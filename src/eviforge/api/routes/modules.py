from __future__ import annotations

from fastapi import APIRouter, Depends

from eviforge.core.auth import ack_dependency, get_current_active_user

router = APIRouter(
    prefix="/modules",
    tags=["modules"],
    dependencies=[Depends(ack_dependency), Depends(get_current_active_user)],
)


@router.get("/catalog")
def modules_catalog() -> dict[str, list[dict[str, object]]]:
    """
    Return module registry metadata used by worker execution.

    This keeps web/desktop UIs in sync with runtime capabilities without
    hardcoding module names client-side.
    """
    out: list[dict[str, object]] = []
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

    out.sort(key=lambda x: str(x.get("name") or ""))
    return {"modules": out}
