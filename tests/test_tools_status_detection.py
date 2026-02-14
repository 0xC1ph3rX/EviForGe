from __future__ import annotations

import subprocess

from eviforge.api.routes import webdev


def test_tool_status_resolves_alias_and_reads_version(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        if name == "alias-tool":
            return "/usr/bin/alias-tool"
        return None

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, "alias-tool 1.2.3\n", "")

    monkeypatch.setattr(webdev.shutil, "which", fake_which)
    monkeypatch.setattr(webdev.subprocess, "run", fake_run)

    data = webdev._tool_status(
        "missing-primary",
        [["--version"]],
        aliases=["alias-tool"],
        category="testing",
    )

    assert data["enabled"] is True
    assert data["path"] == "/usr/bin/alias-tool"
    assert data["version"] == "alias-tool 1.2.3"


def test_tool_status_uses_python_module_fallback(monkeypatch) -> None:
    monkeypatch.setattr(webdev.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        webdev.importlib.util,
        "find_spec",
        lambda name: object() if name == "mockvol" else None,
    )

    data = webdev._tool_status(
        "missing-tool",
        [["--help"]],
        category="memory",
        python_module_fallback="mockvol",
        python_cmd_fallback="python -m mockvol.cli",
    )

    assert data["enabled"] is True
    assert data["path"] == "python -m mockvol.cli"
    assert data["version"] == "python:mockvol"


def test_probe_tool_version_skips_invalid_binwalk_probe(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_run(cmd, capture_output, text, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return subprocess.CompletedProcess(
                cmd,
                1,
                "General Error: Cannot open file --version (CWD: /tmp)\n",
                "",
            )
        return subprocess.CompletedProcess(cmd, 0, "Binwalk v2.4.3\n", "")

    monkeypatch.setattr(webdev.subprocess, "run", fake_run)

    version = webdev._probe_tool_version("/usr/bin/binwalk", [["--version"], ["-h"]])
    assert version == "Binwalk v2.4.3"

