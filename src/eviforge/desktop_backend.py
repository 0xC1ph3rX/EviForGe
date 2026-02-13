from __future__ import annotations

import csv
import json
import logging
import traceback
from pathlib import Path
from typing import Any

from eviforge.config import load_settings
from eviforge.core.custody import append_entry
from eviforge.core.db import create_session_factory, utcnow
from eviforge.core.ingest import ingest_file
from eviforge.core.models import Case, Evidence, Job, JobStatus
from eviforge.core.sanitize import sanitize_text
from eviforge.worker import MODULE_REGISTRY, ensure_modules_registered

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = {
    "job_execution": "auto",
    "max_preview_rows": 2000,
}


class DesktopBackend:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.vault_dir.mkdir(parents=True, exist_ok=True)
        self.SessionLocal = create_session_factory(self.settings.database_url)
        self.profile_path = self.settings.data_dir / "desktop_profiles.json"
        self._configure_logging()

    def _configure_logging(self) -> None:
        log_path = self.settings.data_dir / "desktop.log"
        root = logging.getLogger("eviforge.desktop")
        if root.handlers:
            return
        root.setLevel(logging.INFO)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root.addHandler(handler)

    def available_modules(self) -> list[dict[str, Any]]:
        ensure_modules_registered()
        out: list[dict[str, Any]] = []
        for name in sorted(MODULE_REGISTRY.keys()):
            mod = MODULE_REGISTRY[name]()
            out.append(
                {
                    "name": mod.name,
                    "description": mod.description,
                    "requires_evidence": bool(mod.requires_evidence),
                }
            )
        return out

    def list_cases(self) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            rows = session.query(Case).order_by(Case.created_at.desc()).all()
            return [
                {"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()}
                for c in rows
            ]

    def create_case(self, name: str, *, actor: str = "desktop") -> dict[str, Any]:
        case_name = (name or "").strip()
        if not case_name:
            raise ValueError("Case name is required")
        if len(case_name) > 200:
            raise ValueError("Case name is too long")

        with self.SessionLocal() as session:
            c = Case(name=case_name)
            session.add(c)
            session.commit()
            case_id = c.id
            created_at = c.created_at.isoformat()

        case_root = self.settings.vault_dir / case_id
        (case_root / "evidence").mkdir(parents=True, exist_ok=True)
        (case_root / "artifacts").mkdir(parents=True, exist_ok=True)
        (case_root / "manifests").mkdir(parents=True, exist_ok=True)
        append_entry(
            case_root / "chain_of_custody.log",
            actor=actor,
            action="case.create",
            details={"case_id": case_id, "name": case_name},
        )
        return {"id": case_id, "name": case_name, "created_at": created_at}

    def list_evidence(self, case_id: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            rows = (
                session.query(Evidence)
                .filter(Evidence.case_id == case_id)
                .order_by(Evidence.ingested_at.desc())
                .all()
            )
            return [self._evidence_row(e) for e in rows]

    def ingest_evidence(
        self,
        case_id: str,
        source_path: str | Path,
        *,
        actor: str = "desktop",
    ) -> dict[str, Any]:
        src = Path(source_path).expanduser().resolve()
        if not src.exists() or not src.is_file():
            raise FileNotFoundError(f"Evidence file not found: {src}")

        with self.SessionLocal() as session:
            case = session.get(Case, case_id)
            if not case:
                raise ValueError("Case not found")
            ev = ingest_file(session, self.settings, case_id, src, user=actor)
            session.commit()
            return self._evidence_row(ev)

    def list_jobs(self, case_id: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            rows = (
                session.query(Job)
                .filter(Job.case_id == case_id)
                .order_by(Job.created_at.desc())
                .all()
            )
            return [self._job_row(j) for j in rows]

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(Job, job_id)
            if not row:
                raise ValueError("Job not found")
            return self._job_row(row, include_logs=True)

    def submit_module(
        self,
        case_id: str,
        module_name: str,
        *,
        evidence_id: str | None = None,
        params: dict[str, Any] | None = None,
        actor: str = "desktop",
    ) -> str:
        ensure_modules_registered()
        if module_name not in MODULE_REGISTRY:
            raise ValueError(f"Unknown module: {module_name}")

        module = MODULE_REGISTRY[module_name]()
        if module.requires_evidence and not evidence_id:
            raise ValueError("This module requires evidence")

        run_params = dict(params or {})
        if evidence_id:
            run_params["evidence_id"] = evidence_id
        run_params["actor"] = actor

        with self.SessionLocal() as session:
            case = session.get(Case, case_id)
            if not case:
                raise ValueError("Case not found")
            if evidence_id:
                ev = session.get(Evidence, evidence_id)
                if not ev or ev.case_id != case_id:
                    raise ValueError("Evidence not found in selected case")

            job = Job(
                case_id=case_id,
                evidence_id=evidence_id,
                tool_name=module_name,
                status=JobStatus.PENDING,
                queued_at=utcnow(),
                created_at=utcnow(),
                params_json=json.dumps(run_params, sort_keys=True),
                rq_job_id=f"desktop-inline:{utcnow().timestamp()}",
            )
            session.add(job)
            session.commit()
            job_id = job.id

        append_entry(
            self.settings.vault_dir / case_id / "chain_of_custody.log",
            actor=actor,
            action="job.enqueue",
            details={"job_id": job_id, "module": module_name, "evidence_id": evidence_id},
        )

        import threading

        t = threading.Thread(
            target=self._execute_job,
            args=(job_id, module_name, evidence_id, run_params, actor),
            daemon=True,
            name=f"desktop-job-{job_id[:8]}",
        )
        t.start()
        return job_id

    def _execute_job(
        self,
        job_id: str,
        module_name: str,
        evidence_id: str | None,
        run_params: dict[str, Any],
        actor: str,
    ) -> None:
        module = MODULE_REGISTRY[module_name]()
        kwargs = dict(run_params)
        kwargs.pop("evidence_id", None)
        kwargs.pop("actor", None)
        kwargs.pop("case_id", None)

        with self.SessionLocal() as session:
            job = session.get(Job, job_id)
            if not job:
                return
            job.status = JobStatus.RUNNING
            job.started_at = utcnow()
            session.add(job)
            session.commit()
            case_id = job.case_id

        try:
            result = module.run(case_id, evidence_id, **kwargs)
            if not isinstance(result, dict):
                raise ValueError("Module returned non-dict result")

            artifacts_root = self.settings.vault_dir / case_id / "artifacts"
            output_files = self._extract_output_files(result, artifacts_root=artifacts_root)
            preview = self._result_preview(result)

            with self.SessionLocal() as session:
                job = session.get(Job, job_id)
                if not job:
                    return
                job.status = JobStatus.COMPLETED
                job.completed_at = utcnow()
                job.result_json = json.dumps(result, sort_keys=True)
                job.result_preview_json = json.dumps(preview, sort_keys=True)
                job.output_files_json = json.dumps(output_files)
                session.add(job)
                session.commit()

            append_entry(
                self.settings.vault_dir / case_id / "chain_of_custody.log",
                actor=actor,
                action="job.complete",
                details={
                    "job_id": job_id,
                    "module": module_name,
                    "evidence_id": evidence_id,
                    "output_files": output_files,
                },
            )
        except Exception as exc:
            err = sanitize_text(f"{exc}\n{traceback.format_exc()}")
            logger.exception("Desktop module execution failed: job_id=%s", job_id)
            with self.SessionLocal() as session:
                job = session.get(Job, job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.completed_at = utcnow()
                    job.error_message = err
                    session.add(job)
                    session.commit()
            append_entry(
                self.settings.vault_dir / case_id / "chain_of_custody.log",
                actor=actor,
                action="job.failed",
                details={
                    "job_id": job_id,
                    "module": module_name,
                    "evidence_id": evidence_id,
                    "error": str(exc),
                },
            )

    def read_artifact_rows(self, case_id: str, rel_path: str) -> list[dict[str, Any]]:
        target = self._artifact_file(case_id, rel_path)
        ext = target.suffix.lower()
        max_rows = int(self.get_active_profile().get("max_preview_rows", 2000))

        if ext == ".json":
            obj = json.loads(target.read_text(encoding="utf-8", errors="replace") or "null")
            rows = self._json_to_rows(obj)
            return rows[:max_rows]

        if ext == ".jsonl":
            out: list[dict[str, Any]] = []
            for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    item = {"_raw": line}
                out.append(item if isinstance(item, dict) else {"value": item})
                if len(out) >= max_rows:
                    break
            return out

        if ext == ".csv":
            out: list[dict[str, Any]] = []
            with target.open("r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    out.append({k: row.get(k) for k in reader.fieldnames or []})
                    if len(out) >= max_rows:
                        break
            return out

        out = []
        for i, line in enumerate(
            target.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            out.append({"line": i, "text": line})
            if len(out) >= max_rows:
                break
        return out

    def filter_rows(self, rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        q = (query or "").strip().lower()
        if not q:
            return rows
        terms = [t for t in q.split(" ") if t]
        if not terms:
            return rows
        out: list[dict[str, Any]] = []
        for row in rows:
            text = json.dumps(row, sort_keys=True, ensure_ascii=False).lower()
            if all(t in text for t in terms):
                out.append(row)
        return out

    def export_rows(self, rows: list[dict[str, Any]], target: str | Path) -> Path:
        p = Path(target).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)

        if p.suffix.lower() == ".json":
            p.write_text(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            return p

        # default CSV
        cols: list[str] = []
        for row in rows:
            for k in row.keys():
                if k not in cols:
                    cols.append(k)
        with p.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: self._cell_value(row.get(k)) for k in cols})
        return p

    def get_active_profile(self) -> dict[str, Any]:
        store = self._load_profiles()
        active = str(store.get("active", "default"))
        profiles = store.get("profiles", {})
        prof = profiles.get(active) or DEFAULT_PROFILE
        merged = dict(DEFAULT_PROFILE)
        merged.update(prof)
        return merged

    def list_profile_names(self) -> list[str]:
        store = self._load_profiles()
        profiles = store.get("profiles", {})
        names = sorted(str(k) for k in profiles.keys())
        return names or ["default"]

    def save_profile(self, name: str, values: dict[str, Any], *, set_active: bool = True) -> None:
        profile_name = (name or "").strip() or "default"
        store = self._load_profiles()
        profiles = store.setdefault("profiles", {})
        base = dict(DEFAULT_PROFILE)
        base.update(profiles.get(profile_name, {}))
        base.update(values or {})
        profiles[profile_name] = base
        if set_active:
            store["active"] = profile_name
        self.profile_path.write_text(
            json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load_profiles(self) -> dict[str, Any]:
        if not self.profile_path.exists():
            return {"active": "default", "profiles": {"default": dict(DEFAULT_PROFILE)}}
        try:
            data = json.loads(self.profile_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("invalid profile data")
            if "profiles" not in data or not isinstance(data["profiles"], dict):
                data["profiles"] = {"default": dict(DEFAULT_PROFILE)}
            if "active" not in data:
                data["active"] = "default"
            return data
        except Exception:
            return {"active": "default", "profiles": {"default": dict(DEFAULT_PROFILE)}}

    def _artifact_file(self, case_id: str, rel_path: str) -> Path:
        safe = (rel_path or "").strip().replace("\\", "/")
        if not safe or safe.startswith("/") or ".." in safe.split("/"):
            raise ValueError("Invalid artifact path")
        root = (self.settings.vault_dir / case_id / "artifacts").resolve()
        target = (root / safe).resolve()
        if root not in target.parents and target != root:
            raise ValueError("Artifact path traversal detected")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Artifact not found: {safe}")
        return target

    def _evidence_row(self, ev: Evidence) -> dict[str, Any]:
        return {
            "id": ev.id,
            "filename": Path(ev.path).name,
            "size": ev.size_bytes,
            "sha256": ev.sha256,
            "md5": ev.md5,
            "ingested_at": ev.ingested_at.isoformat(),
            "vault_relpath": ev.path,
        }

    def _job_row(self, job: Job, *, include_logs: bool = False) -> dict[str, Any]:
        output_files: list[str] = []
        if job.output_files_json:
            try:
                output_files = json.loads(job.output_files_json) or []
            except Exception:
                output_files = []

        preview = None
        if job.result_preview_json:
            try:
                preview = json.loads(job.result_preview_json)
            except Exception:
                preview = None

        out = {
            "id": job.id,
            "case_id": job.case_id,
            "evidence_id": job.evidence_id,
            "module": job.tool_name,
            "status": job.status.value if isinstance(job.status, JobStatus) else str(job.status),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "output_files": output_files,
            "preview": preview,
            "error": job.error_message,
        }
        if include_logs:
            out["stdout"] = job.stdout_text
            out["stderr"] = job.stderr_text
            if job.result_json:
                try:
                    out["result"] = json.loads(job.result_json)
                except Exception:
                    out["result"] = None
        return out

    def _extract_output_files(self, result: dict[str, Any], *, artifacts_root: Path) -> list[str]:
        out: list[str] = []
        output_file = result.get("output_file")
        if isinstance(output_file, str):
            try:
                p = Path(output_file).resolve()
                out.append(p.relative_to(artifacts_root.resolve()).as_posix())
            except Exception:
                pass
        output_files = result.get("output_files")
        if isinstance(output_files, list):
            for item in output_files:
                if isinstance(item, str):
                    try:
                        p = Path(item).resolve()
                        out.append(p.relative_to(artifacts_root.resolve()).as_posix())
                    except Exception:
                        continue
        seen = set()
        uniq: list[str] = []
        for p in out:
            if p in seen:
                continue
            seen.add(p)
            uniq.append(p)
        return uniq

    def _result_preview(self, result: dict[str, Any]) -> dict[str, Any]:
        preview: dict[str, Any] = {}
        keys = (
            "status",
            "error",
            "file_count",
            "count",
            "event_count",
            "events_count",
            "messages_count",
            "parsed_objects",
            "tags_found",
            "entropy",
            "is_suspicious",
            "integrity_ok",
        )
        for key in keys:
            if key in result:
                preview[key] = result.get(key)
        if "output_file" in result:
            preview["output_file"] = result.get("output_file")
        return preview

    def _json_to_rows(self, obj: Any) -> list[dict[str, Any]]:
        if isinstance(obj, list):
            return [r if isinstance(r, dict) else {"value": r} for r in obj]

        if isinstance(obj, dict):
            keys = (
                "events",
                "files",
                "rows",
                "matches",
                "messages",
                "dns",
                "http",
                "tls",
                "flows",
                "endpoints",
                "strings",
            )
            for key in keys:
                val = obj.get(key)
                if isinstance(val, list):
                    out = []
                    for item in val:
                        if isinstance(item, dict):
                            row = dict(item)
                        else:
                            row = {"value": item}
                        row.setdefault("_section", key)
                        out.append(row)
                    return out
            return [obj]

        return [{"value": obj}]

    def _cell_value(self, value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return value
