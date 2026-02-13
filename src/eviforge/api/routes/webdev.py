from __future__ import annotations

from pathlib import Path
import importlib
import shutil
import subprocess
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt

from eviforge.core.auth import ALGORITHM, SECRET_KEY
from eviforge.config import ACK_TEXT, load_settings
from eviforge.core.db import create_session_factory, get_setting
from eviforge.core.models import AuditLog, User

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _web_user_from_cookie(request: Request) -> User | None:
    raw = request.cookies.get("access_token")
    if not raw:
        return None
    token = raw[7:] if raw.startswith("Bearer ") else raw
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            return None
    except JWTError:
        return None

    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        return session.query(User).filter(User.username == username).first()


@router.get("/login", response_class=HTMLResponse)
async def web_login(request: Request):
    next_url = request.query_params.get("next")
    return templates.TemplateResponse(request, "admin/login.html", {"next": next_url})


@router.get("", response_class=HTMLResponse)
async def web_index(request: Request):
    """
    Serve the main case dashboard.
    """
    if getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/web/setup", status_code=302)
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/cases/{case_id}", response_class=HTMLResponse)
async def web_case_detail(request: Request, case_id: str):
    """
    Serve the case details page.
    """
    return templates.TemplateResponse(request, "case.html", {"case_id": case_id})


@router.get("/ack", response_class=HTMLResponse)
async def web_ack(request: Request):
    next_url = request.query_params.get("next")
    return templates.TemplateResponse(request, "ack.html", {"next": next_url})


@router.get("/osint", response_class=HTMLResponse)
async def web_osint(request: Request):
    return templates.TemplateResponse(request, "osint.html", {})

@router.get("/setup", response_class=HTMLResponse)
async def web_setup(request: Request):
    return templates.TemplateResponse(request, "setup.html", {})


def _redact_url(url: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user, _pw = creds.split(":", 1)
        return f"{scheme}://{user}:***@{host}"
    return f"{scheme}://***@{host}"


def _tool_status(name: str, version_args: list[str] | None = None, *, category: str = "general") -> dict:
    path = shutil.which(name)
    if not path:
        return {"name": name, "enabled": False, "path": None, "version": None, "category": category}
    version = None
    if version_args:
        try:
            p = subprocess.run([path, *version_args], capture_output=True, text=True, timeout=2)
            out = (p.stdout or p.stderr or "").strip().splitlines()
            version = out[0] if out else None
        except Exception:
            version = None
    return {"name": name, "enabled": True, "path": path, "version": version, "category": category}


def _python_module_status(import_name: str, display_name: str | None = None, *, category: str = "python") -> dict:
    try:
        ok = importlib.util.find_spec(import_name) is not None
    except Exception:
        ok = False
    return {
        "name": display_name or import_name,
        "enabled": ok,
        "path": f"python:{import_name}" if ok else None,
        "version": None,
        "category": category,
    }


def _all_tool_statuses() -> list[dict]:
    return [
        _tool_status("file", ["--version"], category="filesystem"),
        _tool_status("strings", ["--version"], category="filesystem"),
        _tool_status("sha256sum", ["--version"], category="integrity"),
        _tool_status("md5sum", ["--version"], category="integrity"),
        _tool_status("xxd", ["-h"], category="filesystem"),
        _tool_status("exiftool", ["-ver"], category="artifact"),
        _tool_status("jq", ["--version"], category="analysis"),
        _tool_status("rg", ["--version"], category="analysis"),
        _tool_status("yara", ["--version"], category="threat"),
        _tool_status("tshark", ["--version"], category="network"),
        _tool_status("tcpdump", ["--version"], category="network"),
        _tool_status("zeek", ["--version"], category="network"),
        _tool_status("suricata", ["--build-info"], category="network"),
        _tool_status("foremost", ["-V"], category="carving"),
        _tool_status("bulk_extractor", ["-h"], category="carving"),
        _tool_status("binwalk", ["--version"], category="carving"),
        _tool_status("ssdeep", ["-V"], category="integrity"),
        _tool_status("vol", ["--help"], category="memory"),
        _tool_status("volatility3", ["--help"], category="memory"),
        _python_module_status("Evtx.Evtx", "python:Evtx.Evtx", category="python"),
        _python_module_status("Registry", "python:Registry", category="python"),
        _python_module_status("yara", "python:yara", category="python"),
        _python_module_status("pyshark", "python:pyshark", category="python"),
        _python_module_status("volatility3", "python:volatility3", category="python"),
        _python_module_status("scapy", "python:scapy", category="python"),
        _python_module_status("pandas", "python:pandas", category="python"),
    ]


def _collect_forensic_modules() -> list[dict[str, Any]]:
    """
    Source module metadata from the same registry used by worker execution so
    admin sees exactly what this runtime can run.
    """
    out: list[dict[str, Any]] = []
    try:
        from eviforge.worker import MODULE_REGISTRY, ensure_modules_registered

        ensure_modules_registered()
        for reg_name in sorted(MODULE_REGISTRY.keys()):
            cls = MODULE_REGISTRY[reg_name]
            try:
                inst = cls()
                out.append(
                    {
                        "name": getattr(inst, "name", reg_name),
                        "description": getattr(inst, "description", ""),
                        "requires_evidence": bool(getattr(inst, "requires_evidence", True)),
                        "available": True,
                    }
                )
            except Exception as exc:
                out.append(
                    {
                        "name": reg_name,
                        "description": f"Module unavailable in this runtime: {exc}",
                        "requires_evidence": True,
                        "available": False,
                    }
                )
    except Exception as exc:
        out.append(
            {
                "name": "module-registry",
                "description": f"Failed to load module registry: {exc}",
                "requires_evidence": False,
                "available": False,
            }
        )

    out.sort(key=lambda x: str(x["name"]))
    return out


def _build_tools_analytics(tools: list[dict[str, Any]], modules: list[dict[str, Any]]) -> dict[str, Any]:
    tools_by_category: dict[str, int] = {}
    tools_enabled_by_category: dict[str, int] = {}
    for tool in tools:
        category = str(tool.get("category") or "general")
        tools_by_category[category] = tools_by_category.get(category, 0) + 1
        if tool.get("enabled"):
            tools_enabled_by_category[category] = tools_enabled_by_category.get(category, 0) + 1

    module_requires_evidence = sum(1 for m in modules if bool(m.get("requires_evidence")))
    module_available = sum(1 for m in modules if bool(m.get("available")))

    return {
        "tools_total": len(tools),
        "tools_enabled": sum(1 for t in tools if bool(t.get("enabled"))),
        "tools_by_category": tools_by_category,
        "tools_enabled_by_category": tools_enabled_by_category,
        "modules_total": len(modules),
        "modules_available": module_available,
        "modules_requires_evidence": module_requires_evidence,
    }


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def web_job_detail(request: Request, job_id: str):
    return templates.TemplateResponse(request, "job.html", {"job_id": job_id})


@router.get("/admin/tools-data")
async def web_admin_tools_data(request: Request):
    user = _web_user_from_cookie(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    tools = _all_tool_statuses()
    modules = _collect_forensic_modules()
    return {
        "tools": tools,
        "forensic_modules": modules,
        "analytics": _build_tools_analytics(tools, modules),
    }


@router.get("/admin", response_class=HTMLResponse)
async def web_admin(request: Request):
    user = _web_user_from_cookie(request)
    if not user:
        next_url = request.url.path
        return RedirectResponse(url=f"/web/login?next={next_url}", status_code=302)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")

    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        ack = get_setting(session, "authorization_ack")
        audit_log = session.query(AuditLog).order_by(AuditLog.ts.desc()).limit(50).all()

    tools = _all_tool_statuses()

    forensic_modules = _collect_forensic_modules()

    ctx = {
        "ack_required": ACK_TEXT,
        "acknowledged": ack is not None,
        "user": user,
        "data_dir": str(settings.data_dir),
        "vault_dir": str(settings.vault_dir),
        "database_url": _redact_url(settings.database_url),
        "redis_url": _redact_url(settings.redis_url),
        "tools": tools,
        "forensic_modules": forensic_modules,
        "audit_log": audit_log,
    }
    return templates.TemplateResponse(request, "admin.html", ctx)


def _osint_tool_statuses() -> list[dict[str, Any]]:
    return [
        _tool_status("whois", ["--version"], category="osint"),
        _tool_status("dig", ["-v"], category="dns"),
        _tool_status("host", ["-V"], category="dns"),
        _tool_status("nslookup", [], category="dns"),
        _tool_status("curl", ["--version"], category="http"),
        _tool_status("wget", ["--version"], category="http"),
        _tool_status("tor", ["--version"], category="privacy"),
        _tool_status("python3", ["--version"], category="runtime"),
        _python_module_status("dns", "python:dns", category="python"),
        _python_module_status("requests", "python:requests", category="python"),
        _python_module_status("aiohttp", "python:aiohttp", category="python"),
    ]


def _build_osint_analytics(tools: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, int] = {}
    enabled_by_category: dict[str, int] = {}
    missing: list[str] = []
    for tool in tools:
        category = str(tool.get("category") or "general")
        by_category[category] = by_category.get(category, 0) + 1
        if tool.get("enabled"):
            enabled_by_category[category] = enabled_by_category.get(category, 0) + 1
        else:
            missing.append(str(tool.get("name") or "unknown"))

    return {
        "tools_total": len(tools),
        "tools_enabled": sum(1 for t in tools if bool(t.get("enabled"))),
        "tools_missing": sorted(missing),
        "tools_by_category": by_category,
        "tools_enabled_by_category": enabled_by_category,
    }


@router.get("/osint/tools-data")
async def web_osint_tools_data(request: Request):
    user = _web_user_from_cookie(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tools = _osint_tool_statuses()
    resources = [
        {"name": "FaceCheck - Remove My Photos", "url": "https://facecheck.id/removemyphotos", "category": "photo_removal"},
        {"name": "FTC Consumer Advice", "url": "https://www.consumer.ftc.gov/", "category": "privacy"},
        {"name": "Have I Been Pwned", "url": "https://haveibeenpwned.com/", "category": "breach"},
    ]
    return {
        "tools": tools,
        "analytics": _build_osint_analytics(tools),
        "resources": resources,
        "role": user.role,
    }
