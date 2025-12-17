# EviForge

EviForge is a **local-first, offline-capable** DFIR evidence platform with a server-rendered web UI, REST API, and a background worker pipeline for forensic modules. It is designed for **authorized, defensive** investigations only.

## Safety / scope (non-negotiable)

- Authorized use only. First run requires acknowledgement: “I confirm I have legal authorization to process this evidence.”
- No offensive features: no exploitation, persistence, stealth, credential theft, or bypassing access controls.
- Evidence is treated as **read-only**: ingest copies evidence into the case vault; analysis operates on the copied vault.
- Offline-first: no telemetry; no cloud uploads.

## Quickstart (Docker, local)

1) Create `.env`:
```bash
cp .env.example .env
```
Edit `.env` and set at least:
- `EVIFORGE_ADMIN_PASSWORD` (long passphrase)
- `EVIFORGE_SECRET_KEY` (long random secret)

2) Start the stack (Docker may require `sudo`):
```bash
sudo docker compose up -d --build
```

3) Open:
- Web UI: `http://127.0.0.1:8000/web`
- API docs: `http://127.0.0.1:8000/api/docs`
- Health: `http://127.0.0.1:8000/api/health`

4) First run flow:
- Login at `/web/login` (username `admin`, password from `.env`)
- Complete the authorization acknowledgement at `/web/ack`
- Create a case → ingest evidence (from `./import` or upload) → run a module → browse artifacts

## Production (Caddy reverse proxy)

```bash
cp .env.example .env
# Set: DOMAIN_NAME, POSTGRES_PASSWORD, EVIFORGE_DATABASE_URL, EVIFORGE_SECRET_KEY, EVIFORGE_ADMIN_PASSWORD
sudo docker compose -f docker-compose.prod.yml up -d --build
```

## Architecture (text diagram)

- `api` (FastAPI): REST API + server-rendered UI (`/web`) + static assets (`/static`)
- `worker` (RQ): executes module jobs and writes outputs under the case vault
- `db` (Postgres): users, cases, evidence, jobs, audit logs, findings
- `redis`: job queue + (optional) rate-limit storage
- `tika` (optional): document parsing for `parse_text`
- `vault` (filesystem): evidence copies + artifacts per case

## API summary

- Auth:
  - `POST /api/auth/token` (login)
  - `POST /api/auth/ack` (authorization acknowledgement)
- Cases:
  - `GET /api/cases`
  - `POST /api/cases`
  - `GET /api/cases/{case_id}`
- Evidence:
  - `GET /api/cases/{case_id}/evidence`
  - `POST /api/cases/{case_id}/evidence` (ingest from `/import`)
  - `POST /api/cases/{case_id}/evidence/upload` (multipart upload → ingest)
- Jobs:
  - `POST /api/cases/{case_id}/jobs`
  - `GET /api/cases/{case_id}/jobs`
  - `GET /api/jobs/{job_id}`
- Artifacts:
  - `GET /api/cases/{case_id}/artifacts/tree?path=...`
  - `GET /api/cases/{case_id}/artifacts/file?path=...`

## Forensic defensibility

- Evidence copy verification: MD5 + SHA-256 computed at ingest.
- Chain-of-custody: append-only, hash-chained `chain_of_custody.log` per case.
- Audit log: API actions recorded in the database (best-effort).

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
python -m pytest -q
```
