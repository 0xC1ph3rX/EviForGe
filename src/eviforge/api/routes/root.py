from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/web", status_code=307)


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
