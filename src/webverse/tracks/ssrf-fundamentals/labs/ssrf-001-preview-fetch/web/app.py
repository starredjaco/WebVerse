from urllib.parse import urlparse
import os

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

BLOCKLIST = {"localhost", "127.0.0.1", "::1"}
MAX_PREVIEW_BYTES = 4000


def _is_blocked(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
    except Exception:
        return True, "Invalid URL"

    if parsed.scheme not in {"http", "https"}:
        return True, "Only http/https URLs are allowed"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return True, "Missing hostname"

    if host in BLOCKLIST:
        return True, f"Host '{host}' is blocked"

    return False, ""


@app.get("/")
def index():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Preview Fetch</title>
  <style>
    body { font-family: Inter, Arial, sans-serif; max-width: 920px; margin: 40px auto; background: #0b0b0b; color: #f1f1f1; }
    .card { background: #131313; border: 1px solid #2a2a2a; border-radius: 14px; padding: 18px; }
    input { width: 70%; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0f0f0f; color: #fff; }
    button { padding: 10px 14px; border-radius: 8px; border: 1px solid #7d6220; background: #d4af37; color: #000; font-weight: 700; cursor: pointer; }
    pre { white-space: pre-wrap; background: #0d0d0d; border: 1px solid #222; padding: 12px; border-radius: 10px; }
    code { background: #111; padding: 2px 6px; border-radius: 6px; }
    .muted { color: #b0b0b0; }
  </style>
</head>
<body>
  <div class="card">
    <h1>URL Preview Fetch</h1>
    <p class="muted">Enter a URL and the server will fetch it to generate a preview.</p>
    <form id="f">
      <input id="u" name="url" value="https://example.com" />
      <button type="submit">Preview</button>
    </form>
    <p class="muted">Naive protection blocks <code>localhost</code> and <code>127.0.0.1</code>.</p>
    <h3>Response</h3>
    <pre id="out">(nothing fetched yet)</pre>
  </div>
  <script>
    const f = document.getElementById('f');
    const u = document.getElementById('u');
    const out = document.getElementById('out');
    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      out.textContent = 'Loading...';
      try {
        const r = await fetch('/api/preview?url=' + encodeURIComponent(u.value));
        const data = await r.json();
        out.textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        out.textContent = 'Request failed: ' + err;
      }
    });
  </script>
</body>
</html>
"""


@app.get("/api/preview")
def preview():
    target = request.args.get("url", "")
    blocked, reason = _is_blocked(target)
    if blocked:
        return jsonify({"ok": False, "error": reason}), 400

    try:
        r = requests.get(target, timeout=4, allow_redirects=True)
        body = r.text[:MAX_PREVIEW_BYTES]
        return jsonify(
            {
                "ok": True,
                "fetched_url": r.url,
                "status_code": r.status_code,
                "headers": {"content-type": r.headers.get("content-type", "")},
                "body": body,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@app.get("/healthz")
def healthz():
    host = os.getenv("INTERNAL_METADATA_HOST", "metadata")
    port = os.getenv("INTERNAL_METADATA_PORT", "5001")
    return jsonify({"ok": True, "metadata_service": f"{host}:{port}"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
