# OrbitDesk (WebVerse Lab)

**OrbitDesk** is a realistic client portal / document workflow SaaS. Users can register, create projects, share documents, and test integrations.

- **Domain:** `orbitdesk.local`
- **Entrypoint:** `http://orbitdesk.local/` (marketing site)
- **Portal:** `http://portal.orbitdesk.local/`
- **Identity:** `http://auth.orbitdesk.local/`
- **API:** `http://api.orbitdesk.local/`
- **Files:** `http://files.orbitdesk.local/`

> Educational use only. This lab is intentionally vulnerable. Do **not** expose it to the internet.

## Intended learning outcomes

- GraphQL enumeration and authorization testing (BOLA-style issues)
- Token/key scoping mistakes and “looks secure but isn’t” patterns
- Signed URL pitfalls (what is and isn't bound to the signature)
- File path traversal in download handlers
- SSRF via webhook/integration testers
- Command injection in internal diagnostics tooling

## Start

This lab is designed to run behind the provided Nginx gateway. WebVerse should handle routing to the `gateway` service.

If running manually:
```bash
docker compose up -d --build
```

Then add hosts entries for:
- `orbitdesk.local`
- `portal.orbitdesk.local`
- `auth.orbitdesk.local`
- `api.orbitdesk.local`
- `files.orbitdesk.local`
- `status.orbitdesk.local`
- `docs.orbitdesk.local`
- `ops.orbitdesk.local`
