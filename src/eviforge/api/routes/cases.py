from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from eviforge.core.auth import ack_dependency, get_current_active_user, require_roles
from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Case, Evidence, Job, JobStatus
from eviforge.core.audit import audit_from_user
from eviforge.core.jobs import enqueue_job, execute_job_inline

router = APIRouter(dependencies=[Depends(ack_dependency), Depends(get_current_active_user)])


class CaseCreate(BaseModel):
    name: str


@router.get("")
def list_cases():
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        rows = session.query(Case).order_by(Case.created_at.desc()).all()
        return [{"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()} for c in rows]


@router.get("/stats/overview")
def case_overview_stats():
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        cases = session.query(Case).count()
        evidence = session.query(Evidence).count()
        jobs_running = session.query(Job).filter(Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])).count()
        return {
            "cases": cases,
            "evidence": evidence,
            "jobs_running": jobs_running,
        }


@router.post("")
def create_case(request: Request, req: CaseCreate, _user=Depends(require_roles("admin", "analyst"))):
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)

    settings.vault_dir.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as session:
        case = Case(name=req.name)
        session.add(case)
        session.commit()

        case_id = case.id
        case_name = case.name
        created_at = case.created_at

    case_vault = settings.vault_dir / case_id
    (case_vault / "evidence").mkdir(parents=True, exist_ok=True)
    (case_vault / "artifacts").mkdir(parents=True, exist_ok=True)
    (case_vault / "manifests").mkdir(parents=True, exist_ok=True)

    from eviforge.core.custody import append_entry

    append_entry(
        case_vault / "chain_of_custody.log",
        actor="system",
        action="case.create",
        details={"case_id": case_id, "name": case_name},
    )

    # Audit (best-effort)
    try:
        with SessionLocal() as session:
            audit_from_user(
                session,
                action="case.create",
                user=_user,
                request=request,
                case_id=case_id,
                details={"name": case_name},
            )
            session.commit()
    except Exception:
        pass

    return {"id": case_id, "name": case_name, "created_at": created_at.isoformat()}


@router.get("/{case_id}")
def get_case(case_id: str):
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        if not case:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Case not found")
        return {
            "id": case.id,
            "name": case.name,
            "created_at": case.created_at.isoformat(),
            "path": str(settings.vault_dir / case.id)
        }


class JobSubmission(BaseModel):
    module: str
    evidence_id: str | None = None
    params: Dict[str, Any] = {}


def _module_requirements() -> dict[str, bool]:
    """
    Build module support map dynamically from worker registry so newly added
    modules become runnable without editing this route.
    """
    try:
        from eviforge.worker import MODULE_REGISTRY, ensure_modules_registered

        ensure_modules_registered()
        out: dict[str, bool] = {}
        for name, cls in MODULE_REGISTRY.items():
            try:
                out[name] = bool(getattr(cls(), "requires_evidence", True))
            except Exception:
                out[name] = True
        return out
    except Exception:
        # Conservative fallback: keep current known module set.
        return {
            "inventory": True,
            "strings": True,
            "timeline": True,
            "parse_text": True,
            "exif": True,
            "triage": True,
            "yara": True,
            "pcap": True,
            "evtx": True,
            "registry": True,
            "browser": True,
            "email": True,
            "bulk": True,
            "carve": True,
            "verify": True,
            "report": False,
        }


@router.get("/{case_id}/jobs")
def list_case_jobs(case_id: str):
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        jobs = session.query(Job).filter(Job.case_id == case_id).order_by(Job.created_at.desc()).all()
        
        res = []
        for j in jobs:
            output_files = []
            if j.output_files_json:
                try:
                    output_files = json.loads(j.output_files_json) or []
                except Exception:
                    output_files = []

            res.append({
                "id": j.id,
                "module": j.tool_name,
                "status": j.status,
                "created_at": j.created_at.isoformat(),
                "output_files": output_files,
                "error": j.error_message
            })
        return res


@router.post("/{case_id}/jobs")
def create_case_job(request: Request, case_id: str, req: JobSubmission, _user=Depends(require_roles("admin", "analyst"))):
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        if not case:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Case not found")

        module_requires_evidence = _module_requirements()
        if req.module not in module_requires_evidence:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Unsupported module")
        if module_requires_evidence[req.module] and not req.evidence_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="evidence_id is required for this module")

        params = req.params.copy()
        if req.evidence_id:
            params["evidence_id"] = req.evidence_id
        params["actor"] = getattr(_user, "username", "api")
        
        try:
            job = enqueue_job(session, settings, case_id, req.module, params)
            session.commit()

            # File-based custody chain (vault/<case_id>/chain_of_custody.log)
            try:
                from eviforge.core.custody import append_entry

                append_entry(
                    settings.vault_dir / case_id / "chain_of_custody.log",
                    actor=params["actor"],
                    action="job.enqueue",
                    details={"job_id": job.id, "module": req.module, "evidence_id": req.evidence_id},
                )
            except Exception:
                pass

            try:
                audit_from_user(
                    session,
                    action="job.submit",
                    user=_user,
                    request=request,
                    case_id=case_id,
                    evidence_id=req.evidence_id,
                    job_id=job.id,
                    details={"module": req.module},
                )
                session.commit()
            except Exception:
                pass

            if (job.rq_job_id or "").startswith("inline:"):
                execute_job_inline(job.id, async_mode=True)

            return {
                "id": job.id,
                "status": job.status,
                "module": job.tool_name,
                "created_at": job.created_at.isoformat(),
            }
        except Exception as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(e))
