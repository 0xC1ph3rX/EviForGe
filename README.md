# EviForge

EviForge is a local-first DFIR platform for authorized investigations:
- FastAPI API + web UI
- Forensic module pipeline (inventory, strings, timeline, triage, pcap, evtx, yara, etc.)
- Chain-of-custody logging and audit logging
- New native desktop interface (`PySide6/Qt`) with Wireshark-style workflow

## Safety and Scope

- Authorized defensive/forensic use only.
- No offensive features (no stealth/persistence/exploitation).
- Evidence is copied into the vault and treated read-only.
- Offline-first; no telemetry or cloud upload.

## What Was Fixed/Completed

- Fixed `/web/admin` crash caused by stale audit-log field names.
- Added real dashboard stats endpoint (`/api/cases/stats/overview`) and wired web dashboard cards.
- Added resilient job execution mode:
  - `EVIFORGE_JOB_EXECUTION=queue` (strict Redis/RQ)
  - `EVIFORGE_JOB_EXECUTION=inline` (runs jobs in-process)
  - `EVIFORGE_JOB_EXECUTION=auto` (queue first, fallback inline)
- Added native desktop app with:
  - Toolbar actions: Open Case, Import Evidence, Run Analysis, Export Results, Settings/Profiles
  - Left panel: cases, evidence, modules, jobs
  - Center panel: artifact/event table
  - Right panel: structured JSON details
  - Search/filter bar for fast triage
- Included OSINT API router in app wiring (was present in code but not mounted).
- Modernized deprecations:
  - Pydantic `ConfigDict(from_attributes=True)`
  - timezone-aware UTC timestamps
- Added `python -m eviforge.cli` execution guard.
- Added regression/feature tests for admin page, stats, inline jobs, and desktop backend.

## Quickstart (Local venv)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test,desktop]"
```

Run tests:
```bash
pytest -q
```

Run API server:
```bash
eviforge api
```

If port `8000` is already in use, run on another port:
```bash
eviforge api --port 8001
```

Install/repair optional DFIR dependencies:
```bash
bash scripts/install_dfir_dependencies.sh
bash scripts/install_dfir_dependencies.sh --apply
```

Open:
- Web UI: `http://127.0.0.1:8000/web`
- API docs: `http://127.0.0.1:8000/api/docs`
- Root path: `http://127.0.0.1:8000/` (redirects to `/web`)
- Admin tools panel: login as admin and open `/web/admin` to see all detected tools and registered forensic modules.
- OSINT tool tracker: open `/web/osint` for case-linked action tracking (provider/type/status/attachments).
- OSINT runtime toolkit panel: `/web/osint` now includes local OSINT/DNS/HTTP tool availability graph + searchable table.
- FaceCheck integration is API-gated:
  - Hidden by default unless API config + probe succeeds.
  - Configure with `EVIFORGE_ENABLE_FACECHECK_SERVICE=1`, `EVIFORGE_FACECHECK_API_URL`, `EVIFORGE_FACECHECK_API_KEY`.
- Command palette is docked on the left workflow side (open with `Ctrl/Cmd+K`).

Local admin login (panel):
```bash
cp .env.example .env
eviforge api
```
- Default local credentials from `.env.example`: `admin / admin`
- `.env` is loaded automatically on startup.
- Existing `admin` users are auto-reconciled to admin role/password from env (`EVIFORGE_ENFORCE_ENV_ADMIN=1`, default).

## Repository Cleanup

Dry-run cleanup of local/runtime artifacts:
```bash
bash scripts/clean_repo_artifacts.sh
```

Apply cleanup:
```bash
bash scripts/clean_repo_artifacts.sh --apply
```

This cleanup intentionally preserves tracked project assets and non-targets such as:
- `.venv/`
- `verify_expansion.py`

## Desktop UI

Start desktop app:
```bash
eviforge-desktop
```

Desktop workflow:
1. Open/import evidence from the top toolbar.
2. Use the Wireshark-style filter bar (`preset + query + apply/clear`).
3. Select cases/evidence/modules/jobs from the searchable sidebar.
4. Run modules from the Module Runner drawer (`Run Selected` with per-module progress).
   - Use `Run All Loaded` in Admin -> Module Orchestrator to queue every available module for the selected case.
5. Inspect rows in the center sortable table and analyze details on the right tabs (`Decoded`, `Raw`, `Metadata`).
6. Export filtered rows to JSON/CSV from the toolbar.

Desktop defaults are saved in `EVIFORGE_DATA_DIR/desktop_profiles.json`.

## Docker Quickstart

```bash
cp .env.example .env
# set EVIFORGE_ADMIN_PASSWORD and EVIFORGE_SECRET_KEY
sudo docker compose up -d --build
```

If you want strict queue mode in containers, keep:
```bash
EVIFORGE_JOB_EXECUTION=queue
```

## Environment Notes

Common variables:
- `EVIFORGE_DATA_DIR` (default `./.eviforge`)
- `EVIFORGE_VAULT_DIR` (default `<data_dir>/vault`)
- `EVIFORGE_DATABASE_URL`
- `EVIFORGE_REDIS_URL`
- `EVIFORGE_JOB_EXECUTION` (`auto|inline|queue`)
- `EVIFORGE_ENABLE_FACECHECK_SERVICE` (`0|1`)
- `EVIFORGE_FACECHECK_API_URL`
- `EVIFORGE_FACECHECK_API_KEY`

## Example API Workflow (Import -> Analyze -> Filter -> Export)

1. Login: `POST /api/auth/token`
2. Acknowledge authorization: `POST /api/auth/ack`
3. Create case: `POST /api/cases`
4. Upload evidence: `POST /api/cases/{case_id}/evidence/upload`
5. Run module: `POST /api/cases/{case_id}/jobs`
6. Track job: `GET /api/jobs/{job_id}`
7. Browse artifacts:
   - `GET /api/cases/{case_id}/artifacts/tree`
   - `GET /api/cases/{case_id}/artifacts/file?path=...`
8. Export by downloading artifact files (`/api/artifacts/{case_id}/{path}`) or via desktop export.

## Changelog (Current Pass)

- Added desktop app and backend service layer.
- Fixed admin/audit route regression.
- Added case overview stats API and dashboard wiring.
- Added robust inline job fallback mode.
- Added tests:
  - `tests/test_web_admin.py`
  - `tests/test_cases_stats.py`
  - `tests/test_jobs_inline_execution.py`
  - `tests/test_desktop_backend.py`

## OS Support

- API/web: Linux/macOS/Windows (Python 3.11+).
- Desktop app: `PySide6` required (`pip install -e ".[desktop]"`).
- Some modules depend on optional external tools (`tshark`, `exiftool`, `yara`, `bulk_extractor`, `foremost`).

## Runtime Notes

- Stop `eviforge api` with `Ctrl+C` (SIGINT) for normal shutdown.
- A `core dumped` message often indicates `SIGQUIT` (`Ctrl+\`) or shell job-control signal, not necessarily an application bug.
