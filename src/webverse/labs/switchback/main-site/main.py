from __future__ import annotations

import os
import time
import urllib.request
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

LAB_DOMAIN = os.getenv("LAB_DOMAIN", "switchback.local")

app = FastAPI(title="Switchback", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def _render(request: Request, template: str, ctx: dict[str, Any], status_code: int = 200):
    base = {"request": request, "lab_domain": LAB_DOMAIN}
    base.update(ctx)
    return templates.TemplateResponse(template, base, status_code=status_code)


def _check(url: str) -> dict[str, Any]:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SwitchbackStatus/1.0"})
        with urllib.request.urlopen(req, timeout=1.2) as r:
            ok = 200 <= r.status < 400
            return {"ok": ok, "ms": int((time.time() - t0) * 1000)}
    except Exception:
        return {"ok": False, "ms": int((time.time() - t0) * 1000)}

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _render(
        request,
        "index.html",
        {
            "title": "Switchback Suite",
        },
    )

@app.get("/products/mail", response_class=HTMLResponse)
def product_mail(request: Request):
    return _render(request, "product_mail.html", {"title": "Mail"})


@app.get("/products/vault", response_class=HTMLResponse)
def product_vault(request: Request):
    return _render(request, "product_vault.html", {"title": "Vault"})


@app.get("/products/partner-api", response_class=HTMLResponse)
def product_partner_api(request: Request):
    return _render(request, "product_api.html", {"title": "Partner API"})


@app.get("/security", response_class=HTMLResponse)
def security(request: Request):
    return _render(request, "security.html", {"title": "Security"})


@app.get("/status", response_class=HTMLResponse)
def status(request: Request):
    # Server-side checks so we don't leak internal hostnames into the browser.
    checks = {
        "marketing": _check("http://127.0.0.1:8000/"),
        "partner_api": _check("http://api:8000/healthz"),
        "mail": _check("http://mail:8000/healthz"),
        "vault": _check("http://vault:8000/healthz"),
    }
    return _render(request, "status.html", {"title": "Status", "checks": checks})


@app.get("/changelog", response_class=HTMLResponse)
def changelog(request: Request):
    return _render(request, "changelog.html", {"title": "Changelog"})


@app.get("/support", response_class=HTMLResponse)
def support(request: Request):
    return _render(request, "support.html", {"title": "Support"})


@app.get("/robots.txt")
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /partners/\n")


@app.get("/sitemap.xml")
def sitemap():
    xml = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
  <url><loc>http://{LAB_DOMAIN}/</loc></url>
  <url><loc>http://{LAB_DOMAIN}/products/mail</loc></url>
  <url><loc>http://{LAB_DOMAIN}/products/vault</loc></url>
  <url><loc>http://{LAB_DOMAIN}/products/partner-api</loc></url>
  <url><loc>http://{LAB_DOMAIN}/security</loc></url>
  <url><loc>http://{LAB_DOMAIN}/status</loc></url>
  <url><loc>http://{LAB_DOMAIN}/changelog</loc></url>
  <url><loc>http://{LAB_DOMAIN}/support</loc></url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.exception_handler(404)
def not_found(request: Request, exc: Exception):
    return _render(request, "error.html", {"title": "Not found", "code": 404}, status_code=404)


@app.exception_handler(500)
def server_error(request: Request, exc: Exception):
    return _render(request, "error.html", {"title": "Error", "code": 500}, status_code=500)
