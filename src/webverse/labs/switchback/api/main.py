from __future__ import annotations

import os
import time

from datetime import datetime
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

LAB_DOMAIN = os.getenv("LAB_DOMAIN", "switchback.local")

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "switchback_app")
DB_USER = os.getenv("DB_USER", "wv_api")
DB_PASSWORD = os.getenv("DB_PASSWORD", "wv_api_pass")

MAIL_DEMO_EMAIL = os.getenv("MAIL_DEMO_EMAIL", "demo@marketing.switchback.local")
MAIL_DEMO_PASS = os.getenv("MAIL_DEMO_PASS", "DemoMail!2026")

APP_VERSION = "2026.2.28"

app = FastAPI(title="Switchback Partner API", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def _render(request: Request, template: str, ctx: dict[str, Any], status_code: int = 200):
    base = {"request": request, "lab_domain": LAB_DOMAIN}
    base.update(ctx)
    return templates.TemplateResponse(template, base, status_code=status_code)


def _connect():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=DictCursor,
        autocommit=True,
    )


def _wait_for_db() -> None:
    last_err: Exception | None = None
    for _ in range(60):
        try:
            conn = _connect()
            conn.close()
            return
        except Exception as e:  # pragma: no cover
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"database not ready: {last_err}")


@app.on_event("startup")
def startup() -> None:
    _wait_for_db()

@app.get("/", response_class=HTMLResponse)
def portal_root(request: Request):
    return _render(
        request,
        "portal_index.html",
        {
            "title": "Partner Portal",
            "version": APP_VERSION,
        },
    )


@app.get("/portal/docs", response_class=HTMLResponse)
def portal_docs(request: Request):
    return _render(
        request,
        "portal_docs.html",
        {
            "title": "Partner API Docs",
            "mail_demo_email": MAIL_DEMO_EMAIL,
            "mail_demo_pass": MAIL_DEMO_PASS,
        },
    )

@app.get("/portal/verify", response_class=HTMLResponse)
def portal_verify_get(request: Request):
    return _render(
        request,
        "portal_verify.html",
        {"title": "Verify referral", "result": None, "code": ""},
    )


@app.post("/portal/verify", response_class=HTMLResponse)
def portal_verify_post(request: Request, code: str = Form(...)):
    code = (code or "").strip()
    result = None

    if code:
        # Safe, partner-facing lookup for staging. This is intentionally separate
        # from the legacy attribution lookup endpoint.
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT code, referrer_email, points, created_at FROM referrals WHERE code=%s LIMIT 1",
            (code,),
        )
        row = cur.fetchone()
        conn.close()
        result = dict(row) if row else None

    return _render(
        request,
        "portal_verify.html",
        {"title": "Verify referral", "result": result, "code": code},
    )


@app.get("/v1/public/status")
def public_status():
    return {"ok": True, "service": "partner-api", "ts": datetime.utcnow().isoformat() + "Z"}


@app.get("/v1/public/version")
def public_version():
    return {"version": APP_VERSION}

@app.get("/v1/referrals", include_in_schema=False)
@app.get("/v1/referrals/", include_in_schema=False)
def referrals_root(request: Request):
    raise HTTPException(status_code=403, detail="Forbidden")

@app.get("/v1/referrals/details", response_class=JSONResponse)
def referral_details(code: str):
    # Safe JSON details endpoint for partners.
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT code, referrer_email, points, created_at FROM referrals WHERE code=%s LIMIT 1",
        (code,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return JSONResponse({"ok": False, "status": "not_found"}, status_code=404)

    # jsonable_encoder converts datetime/Decimal/etc. safely
    payload = {"ok": True, "referral": dict(row)}
    return JSONResponse(content=jsonable_encoder(payload))

@app.get("/v1/referrals/lookup", response_class=JSONResponse)
def referral_lookup(code: str):
    """
    Legacy referral lookup.

    Intentionally vulnerable: the referral code is interpolated into SQL.
    HARDENING CONSTRAINT:
    - Response bodies are constant/generic
    - Errors are swallowed
    - Timing is the only useful signal

    This endpoint simulates a legacy attribution component that was designed
    to minimize data exposure in public contexts.
    """


    constant = {"ok": True, "status": "received"}

    query = f"SELECT code FROM referrals WHERE code = '{code}' LIMIT 1;"

    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(query)
    except Exception:
        return JSONResponse(constant)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return JSONResponse(constant)


@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/docs")
def old_docs_redirect():
    # Prevent obvious /docs discovery; keep a believable portal path.
    return RedirectResponse("/", status_code=302)


@app.exception_handler(404)
def not_found(request: Request, exc: Exception):
    return _render(request, "portal_error.html", {"title": "Not found", "code": 404}, status_code=404)


@app.exception_handler(500)
def server_error(request: Request, exc: Exception):
    return _render(request, "portal_error.html", {"title": "Error", "code": 500}, status_code=500)
