# WebVerse

WebVerse is a **local-first web hacking lab platform** for practicing **realistic web application security** and **API security** attack chains on your own machine.
It’s a desktop app + lab runner that spins up **intentionally vulnerable web apps** using **Docker Compose**, opens them in your browser, and tracks your progress.

> **Educational use only.** Labs are intentionally vulnerable. **Do not expose them to the internet.**

---

## Install (Official / Recommended)

WebVerse installs via the installer script. It’s **idempotent** (safe to rerun) and is the only supported install path documented here.

**Supported distros:** Ubuntu / Debian / Kali (Linux)  
**What it does:** installs deps, ensures Docker + `docker compose` works, installs WebVerse via pipx, and applies the common first-run fixes.

```bash
curl -fsSL https://raw.githubusercontent.com/LeighlinRamsay/WebVerse/refs/heads/main/install.sh | bash
```

After install:

```bash
webverse
```

### Updating WebVerse
Re-run the installer script — it will reinstall/refresh the WebVerse pipx environment safely.

---

## Screenshot / Demo]

<img width="1911" height="887" alt="HOME PAGE NEW" src="https://github.com/user-attachments/assets/49002836-10ca-43ba-983c-1502bd84536c" />

<img width="1907" height="891" alt="PIXEL PIVOT PAGE NEW" src="https://github.com/user-attachments/assets/aac378e8-b0b0-461a-b263-78d3492f7599" />

<img width="1902" height="872" alt="BROWSE LABS PAGE NEW" src="https://github.com/user-attachments/assets/9e48563b-ad83-4ca3-897c-46357861dcf5" />

<img width="1905" height="888" alt="webverse profile page" src="https://github.com/user-attachments/assets/c641734e-4b63-4c7a-8cad-a7c0e4f04948" />

---

## What you get (and why it’s different)

WebVerse is built around **real-world failure chains** you’ll actually encounter during web app pentests:

- **API Authorization Failures**
  - **BOLA / IDOR** (object-level access control)
  - **BOPLA** / **mass assignment** + **excessive data exposure** (property-level)
  - **BFLA** (function-level admin endpoints)
- **Auth & session issues** (JWT, reset flows, role checks, trusted-client assumptions)
- **SSRF pivots** into internal surfaces (subdomains, admin panels, internal APIs)
- **GraphQL recon** (introspection → schema mining → sensitive fields)
- Multi-service apps with realistic separation (portal, API, internal ops, dashboards)

Everything runs locally via Docker Compose, so you can:
- iterate quickly,
- break things safely,
- reset cleanly,
- and practice the same technique across multiple stacks.

---

## How WebVerse works

1. Launch WebVerse (`webverse`)
2. Browse labs (difficulty + topics)
3. Start a lab (Docker Compose spins up the full stack)
4. Open it in your browser (entrypoint + subdomains)
5. Chain the bugs, capture the flag, submit to mark it solved
6. Reset and rerun the lab whenever you want

Progress is tracked via our API and backend at api-opensource.webverselabs.com this way we can support WebVerse accounts and ensure your lab progress will always be saved!

---

## Links

- WebVerse Labs site: https://webverselabs.com
- Blog / writeups: https://blog.webverselabs.com

---

## Disclaimer

WebVerse and included labs are for **education and authorized testing only**.
You are responsible for how you use this software.
