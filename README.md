# WebVerse

WebVerse is a local **web & API security lab runner**: a desktop app that discovers labs in `./labs/`, starts them with **Docker Compose**, opens them in your browser, and tracks your progress — all on your own machine.

> **Educational use only.** Labs are intentionally vulnerable. Do **not** expose them to the internet.

---

## Screenshot / Demo


<img width="1915" height="897" alt="Screenshot 2026-01-27 005040" src="https://github.com/user-attachments/assets/c977fe06-3d95-4b66-bc79-6f5af223ebc8" />


<img width="1908" height="888" alt="Screenshot 2026-01-26 152925" src="https://github.com/user-attachments/assets/ff5b099b-70e1-4ac8-a41b-bdeadaaa9ddf" />


<img width="1916" height="887" alt="Screenshot 2026-01-26 153009" src="https://github.com/user-attachments/assets/86dce2a3-44f5-4aae-98b9-0e41d00b723f" />



---

## Why WebVerse?

Most practice environments are either:
- too heavy to set up,
- too scattered across repos,
- or too “manual” to run repeatedly.

WebVerse is built to make local practice **repeatable**:
- labs are self-contained
- starting/resetting takes one click
- you can iterate quickly, break things, reset, and try again

---

## Features

- 🧪 Browse included labs (name, difficulty, description, tags)
- ▶️ One-click **Start / Stop / Reset**
- 🌐 **Open in Browser** from the UI
- 🧾 View lab status and logs
- ✅ Track progress locally (`progress.db`)
- 🏁 Flag submission + verification (via `flag_sha256` in each `lab.yml`)

---

## Requirements

- **Linux or macOS**
- **Python 3.10+**
- **Docker** + **Docker Compose**
  - Linux: Docker Engine + Compose plugin
  - macOS: Docker Desktop

Install Python deps:

```bash
pip install -r requirements.txt
