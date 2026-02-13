from __future__ import annotations

import time
from pathlib import Path

import pytest

from eviforge.desktop_backend import DesktopBackend


@pytest.fixture()
def backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DesktopBackend:
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "eviforge.sqlite"

    monkeypatch.setenv("EVIFORGE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("EVIFORGE_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("EVIFORGE_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("EVIFORGE_JOB_EXECUTION", "inline")
    return DesktopBackend()


def test_desktop_backend_case_ingest_run_export(backend: DesktopBackend, tmp_path: Path) -> None:
    case = backend.create_case("Desktop Case")
    source = tmp_path / "sample.bin"
    source.write_bytes(b"forensic-test-data")
    ev = backend.ingest_evidence(case["id"], source)

    job_id = backend.submit_module(case["id"], "verify", evidence_id=ev["id"], params={})

    status = None
    job = None
    for _ in range(40):
        job = backend.get_job(job_id)
        status = job["status"]
        if status in {"COMPLETED", "FAILED"}:
            break
        time.sleep(0.1)

    assert status == "COMPLETED"
    assert job is not None
    assert job["output_files"]

    rows = backend.read_artifact_rows(case["id"], job["output_files"][0])
    assert rows
    assert backend.filter_rows(rows, "integrity")

    json_out = tmp_path / "export.json"
    csv_out = tmp_path / "export.csv"
    backend.export_rows(rows, json_out)
    backend.export_rows(rows, csv_out)
    assert json_out.exists()
    assert csv_out.exists()
