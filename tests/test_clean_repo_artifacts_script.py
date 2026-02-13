from __future__ import annotations

import subprocess
from pathlib import Path


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def test_clean_repo_artifacts_dry_run_and_apply(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run("git", "init", str(repo))

    # Tracked non-targets.
    (repo / "site").mkdir()
    (repo / "site" / "index.html").write_text("tracked site\n", encoding="utf-8")
    (repo / "dump.rdb").write_text("tracked dump\n", encoding="utf-8")
    (repo / "verify_expansion.py").write_text("# tracked helper\n", encoding="utf-8")

    # Tracked files that match cleanup patterns; must be skipped.
    (repo / "tracked.pyc").write_bytes(b"tracked bytecode")
    (repo / "core").write_text("tracked core file\n", encoding="utf-8")
    (repo / "core.keep").write_text("tracked core.* file\n", encoding="utf-8")

    _run("git", "-C", str(repo), "add", ".")

    # Untracked artifacts to clean.
    (repo / ".eviforge").mkdir()
    (repo / ".eviforge" / "desktop.log").write_text("log\n", encoding="utf-8")
    (repo / ".pytest_cache" / "v" / "cache").mkdir(parents=True)
    (repo / ".pytest_cache" / "v" / "cache" / "nodeids").write_text("[]\n", encoding="utf-8")
    (repo / "module" / "__pycache__").mkdir(parents=True)
    (repo / "module" / "__pycache__" / "x.pyc").write_bytes(b"x")
    (repo / "module" / "temp.pyc").write_bytes(b"x")
    (repo / "module" / "temp.pyo").write_bytes(b"x")
    (repo / "core.12345").write_text("untracked core file\n", encoding="utf-8")

    # Explicit non-target.
    (repo / ".venv" / "lib").mkdir(parents=True)
    (repo / ".venv" / "lib" / "keep.pyc").write_bytes(b"venv")

    script = Path(__file__).resolve().parents[1] / "scripts" / "clean_repo_artifacts.sh"

    dry = _run("bash", str(script), "--root", str(repo))
    assert dry.returncode == 0, dry.stderr
    assert "[DRY-RUN] .eviforge" in dry.stdout
    assert "[DRY-RUN] .pytest_cache" in dry.stdout
    assert "[SKIP tracked] tracked.pyc" in dry.stdout
    assert "[SKIP tracked] core" in dry.stdout
    assert "[SKIP tracked] core.keep" in dry.stdout
    assert (repo / ".eviforge").exists()
    assert (repo / "module" / "temp.pyc").exists()
    assert (repo / ".venv" / "lib" / "keep.pyc").exists()

    apply = _run("bash", str(script), "--apply", "--root", str(repo))
    assert apply.returncode == 0, apply.stderr
    assert "[DELETED] .eviforge" in apply.stdout
    assert "[DELETED] .pytest_cache" in apply.stdout
    assert "[DELETED] core.12345" in apply.stdout

    # Removed artifacts.
    assert not (repo / ".eviforge").exists()
    assert not (repo / ".pytest_cache").exists()
    assert not (repo / "module" / "__pycache__").exists()
    assert not (repo / "module" / "temp.pyc").exists()
    assert not (repo / "module" / "temp.pyo").exists()
    assert not (repo / "core.12345").exists()

    # Preserved files.
    assert (repo / ".venv" / "lib" / "keep.pyc").exists()
    assert (repo / "site" / "index.html").exists()
    assert (repo / "dump.rdb").exists()
    assert (repo / "verify_expansion.py").exists()
    assert (repo / "tracked.pyc").exists()
    assert (repo / "core").exists()
    assert (repo / "core.keep").exists()
