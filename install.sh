#!/usr/bin/env bash
set -Eeuo pipefail

# WebVerse battle-tested installer (Ubuntu + Debian)
# - Installs apt deps (git, curl, python, pipx, Qt libs, etc.)
# - Installs Docker (distro packages) ONLY if Docker isn't already present
# - Ensures Docker Compose works (without breaking docker-ce installs)
# - Installs/updates WebVerse via pipx
# - Attempts to remove the “privileged ports” first-run blocker (setcap; sysctl fallback)
# - Idempotent: safe to re-run

# ---------- colors (bright, never “blends”) ----------
RESET=$'\033[0m'
BOLD=$'\033[1m'
PURPLE=$'\033[95m'   # bright magenta/purple
CYAN=$'\033[96m'
GREEN=$'\033[92m'
YELLOW=$'\033[93m'
RED=$'\033[91m'

say()   { printf "%s%s%s\n" "${BOLD}${PURPLE}" "$*" "${RESET}"; }
info()  { printf "%s%s%s %s%s\n" "${BOLD}${PURPLE}" "›" "${RESET}" "${PURPLE}$*${RESET}"; }
ok()    { printf "%s%s%s %s%s\n" "${BOLD}${GREEN}" "✔" "${RESET}" "${PURPLE}$*${RESET}"; }
warn()  { printf "%s%s%s %s%s\n" "${BOLD}${YELLOW}" "!" "${RESET}" "${PURPLE}$*${RESET}"; }
err()   { printf "%s%s%s %s%s\n" "${BOLD}${RED}" "✖" "${RESET}" "${PURPLE}$*${RESET}"; }

LOG="/tmp/webverse-install-$(date +%s).log"
touch "$LOG" && chmod 600 "$LOG" || true

tail_log() {
  warn "Last 80 lines of log: ${CYAN}${LOG}${RESET}"
  tail -n 80 "$LOG" | sed -e "s/^/${PURPLE}/" -e "s/$/${RESET}/"
}

die() {
  err "$*"
  warn "Full log: ${CYAN}${LOG}${RESET}"
  exit 1
}

run() {
  # run "Description..." cmd...
  local desc="$1"; shift
  info "$desc"
  if "$@" >>"$LOG" 2>&1; then
    ok "$desc"
  else
    err "$desc"
    tail_log
    die "Command failed: $*"
  fi
}

run_user() {
  # run_user "Description..." "command string..."
  local desc="$1"; shift
  local cmd="$*"
  info "$desc"
  if as_user "$cmd" >>"$LOG" 2>&1; then
    ok "$desc"
  else
    err "$desc"
    tail_log
    die "Command failed (as ${TARGET_USER}): $cmd"
  fi
}

have() { command -v "$1" >/dev/null 2>&1; }

# ---------- user / sudo handling ----------
TARGET_USER=""
TARGET_HOME=""

resolve_home() {
  local u="$1"
  getent passwd "$u" | cut -d: -f6
}

if [[ "${EUID}" -eq 0 ]]; then
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    TARGET_USER="${SUDO_USER}"
    TARGET_HOME="$(resolve_home "$TARGET_USER")"
  else
    die "Do not run this as root. Run it as your normal user (it uses sudo when needed)."
  fi
else
  TARGET_USER="$(id -un)"
  TARGET_HOME="$HOME"
  if have sudo; then
    info "Requesting sudo (you may be prompted)..."
    sudo -v || die "sudo authentication failed."
  else
    die "sudo not found. Install sudo or run on a system with sudo configured."
  fi
fi

# Run a command as the target user in a login shell (so PATH works like a normal terminal)
as_user() {
  local cmd="$*"
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then
    bash -lc "$cmd"
  else
    sudo -u "$TARGET_USER" -H bash -lc "$cmd"
  fi
}

# ---------- distro detection ----------
if [[ ! -r /etc/os-release ]]; then
  die "Cannot read /etc/os-release (unsupported system)."
fi

. /etc/os-release
DIST_ID="${ID:-}"
DIST_LIKE="${ID_LIKE:-}"

case "$DIST_ID" in
  ubuntu|debian) : ;;
  *)
    # allow “like debian/ubuntu”
    if [[ "$DIST_LIKE" != *debian* && "$DIST_LIKE" != *ubuntu* ]]; then
      die "Unsupported distro: ${DIST_ID:-unknown}. This installer supports Ubuntu/Debian."
    fi
    ;;
esac

say "WebVerse installer (Ubuntu/Debian) — logs: ${CYAN}${LOG}${RESET}"
info "Target user: ${CYAN}${TARGET_USER}${RESET}  Home: ${CYAN}${TARGET_HOME}${RESET}"

# ---------- apt helpers ----------
wait_for_apt_locks() {
  local waited=0
  while sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
        sudo fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
        sudo fuser /var/cache/apt/archives/lock >/dev/null 2>&1; do
    if (( waited == 0 )); then
      warn "apt is locked (unattended upgrades or another apt running). Waiting…"
    fi
    sleep 2
    waited=$((waited + 2))
    if (( waited >= 120 )); then
      die "apt lock did not clear after 120s. Try again after apt finishes."
    fi
  done
}

apt_update() {
  wait_for_apt_locks
  run "Updating apt package lists" sudo apt-get -o Acquire::Retries=3 update
}

pkg_available() {
  apt-cache show "$1" >/dev/null 2>&1
}

apt_install_available() {
  # installs only packages that exist on this distro
  local pkgs=("$@")
  local to_install=()
  for p in "${pkgs[@]}"; do
    if pkg_available "$p"; then
      to_install+=("$p")
    else
      warn "Package not available here (skipping): ${CYAN}${p}${RESET}"
    fi
  done
  if ((${#to_install[@]} > 0)); then
    wait_for_apt_locks
    run "Installing apt dependencies: ${CYAN}${to_install[*]}${RESET}" \
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${to_install[@]}"
  fi
}

# ---------- base deps ----------
apt_update

BASE_PKGS=(
  ca-certificates curl git
  python3 python3-venv python3-pip
  xdg-utils
  libcap2-bin
)

# Qt/X11 runtime libs for PyQt5 (covers the xcb crash you hit)
QT_PKGS=(
  libxcb-xinerama0
  libxkbcommon-x11-0
  libxcb-cursor0
  libxcb-icccm4
  libxcb-image0
  libxcb-keysyms1
  libxcb-randr0
  libxcb-render-util0
  libxcb-shape0
  libxcb-xfixes0
  libxrender1
  libxi6
  libxtst6
  libnss3
  libgl1
)

apt_install_available "${BASE_PKGS[@]}"
apt_install_available "${QT_PKGS[@]}"

# pipx: prefer apt package; fallback to pip user install if not available
if ! have pipx; then
  if pkg_available pipx; then
    apt_install_available pipx
  else
    warn "pipx not available via apt on this system — installing via pip (user install)."
    run "Installing pipx via pip (user)" sudo -u "$TARGET_USER" -H python3 -m pip install --user -U pipx
  fi
fi

# ensure ~/.local/bin is on PATH for future shells
info "Ensuring pipx path is configured (ensurepath)"
if as_user "pipx ensurepath" >>"$LOG" 2>&1; then
  ok "Ensuring pipx path is configured (ensurepath)"
else
  warn "pipx ensurepath failed (continuing). Open a new terminal if 'webverse' isn't found in PATH."
fi

# ---------- Docker + Compose ----------
docker_is_podman() {
  docker --version 2>/dev/null | grep -qi podman
}

docker_compose_works() {
  docker compose version >/dev/null 2>&1
}

docker_works_as_user() {
  as_user "docker ps >/dev/null 2>&1"
}

ensure_docker_service_running() {
  if have systemctl; then
    run "Enabling + starting Docker service" sudo systemctl enable --now docker
  elif have service; then
    run "Starting Docker service (service)" sudo service docker start
  else
    warn "No systemctl/service detected — cannot auto-start docker daemon here."
  fi
}

# If docker is missing, install distro Docker (stable, low-drama)
if ! have docker; then
  warn "Docker not found — installing distro Docker (docker.io)."
  apt_install_available docker.io
  ensure_docker_service_running
else
  ok "Docker found: $(docker --version 2>/dev/null || true)"
  if docker_is_podman; then
    warn "Your 'docker' is actually Podman (podman-docker). WebVerse expects real Docker."
    warn "Removing podman-docker and installing docker.io."
    wait_for_apt_locks
    run "Removing podman-docker" sudo DEBIAN_FRONTEND=noninteractive apt-get remove -y podman-docker || true
    apt_install_available docker.io
    ensure_docker_service_running
  fi
fi

# Ensure Compose works WITHOUT breaking docker-ce users.
if docker_compose_works; then
  ok "Docker Compose works: $(docker compose version 2>/dev/null | head -n 1 || true)"
else
  warn "Docker Compose not working — installing a compatible Compose package."
  # If docker-compose-plugin exists but compose still fails, remove it first (it can be broken/partial)
  if dpkg -s docker-compose-plugin >/dev/null 2>&1; then
    warn "docker-compose-plugin is installed but 'docker compose' failed — removing plugin to repair."
    wait_for_apt_locks
    run "Removing docker-compose-plugin" sudo DEBIAN_FRONTEND=noninteractive apt-get remove -y docker-compose-plugin || true
  fi

  # Prefer docker-compose-v2 when available; fallback to docker-compose
  if pkg_available docker-compose-v2; then
    # If a plugin exists that owns the same path, remove it to avoid overwrite errors
    if dpkg -s docker-compose-plugin >/dev/null 2>&1; then
      wait_for_apt_locks
      run "Removing conflicting docker-compose-plugin" sudo DEBIAN_FRONTEND=noninteractive apt-get remove -y docker-compose-plugin
    fi
    apt_install_available docker-compose-v2
  elif pkg_available docker-compose; then
    apt_install_available docker-compose
  else
    die "Could not find any Compose package (docker-compose-v2/docker-compose)."
  fi

  if docker_compose_works; then
    ok "Docker Compose now works: $(docker compose version 2>/dev/null | head -n 1 || true)"
  else
    die "Docker Compose still not working after install."
  fi
fi

# docker group membership (so user doesn’t need sudo for docker)
if getent group docker >/dev/null 2>&1; then :; else
  run "Creating docker group" sudo groupadd docker || true
fi

if id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
  ok "User is already in docker group."
else
  run "Adding ${CYAN}${TARGET_USER}${RESET} to docker group" sudo usermod -aG docker "$TARGET_USER"
  warn "You must log out/in (or reboot) for docker group membership to take effect."
  warn "Until then, Docker commands may require sudo."
fi

# Verify docker access (best-effort)
if docker_works_as_user; then
  ok "Docker works for ${CYAN}${TARGET_USER}${RESET} (no sudo)."
else
  warn "Docker may not work for ${CYAN}${TARGET_USER}${RESET} yet (likely needs re-login for docker group)."
fi

# ---------- Install / Upgrade WebVerse via pipx ----------
# Always install from the GitHub repo (NOT PyPI), and keep it idempotent.
# You can optionally pin a ref/tag/commit:
#   WEBVERSE_REF=v1.0.0 bash install.sh
WEBVERSE_REPO_URL="${WEBVERSE_REPO_URL:-https://github.com/LeighlinRamsay/WebVerse.git}"
WEBVERSE_REF="${WEBVERSE_REF:-main}"
WEBVERSE_GIT_SPEC="git+${WEBVERSE_REPO_URL}@${WEBVERSE_REF}"

# --force makes this safe to re-run: it will reinstall/replace the existing venv.
run_user "Installing WebVerse via pipx (git: ${WEBVERSE_REF})" "pipx install --force \"${WEBVERSE_GIT_SPEC}\""

# Verify install (as requested)
if as_user "command -v webverse >/dev/null 2>&1"; then
  ok "WebVerse installed: $(as_user "command -v webverse" 2>/dev/null || true)"
else
  # fallback: check default pipx bin location
  if [[ -x "${TARGET_HOME}/.local/bin/webverse" ]]; then
    warn "webverse not found in PATH yet, but exists at: ${CYAN}${TARGET_HOME}/.local/bin/webverse${RESET}"
    warn "Open a new terminal (or log out/in) and try again."
  else
    die "WebVerse installation completed but 'webverse' command not found."
  fi
fi

# ---------- Fix the “privileged ports” blocker (setcap; sysctl fallback) ----------
# Your CLI currently blocks startup if it thinks low-port bind isn't allowed.
# We try to set CAP_NET_BIND_SERVICE on the python actually used.
VENV_PY="${TARGET_HOME}/.local/share/pipx/venvs/webverse/bin/python"

apply_setcap() {
  local py="$1"
  local real
  real="$(readlink -f "$py" 2>/dev/null || echo "$py")"

  if [[ ! -e "$py" ]]; then
    warn "Could not find pipx venv python at: ${CYAN}${py}${RESET} (skipping setcap)."
    return 1
  fi

  info "Attempting to allow low ports via setcap on python…"
  # Try on venv python first; if it fails, try resolved python
  if sudo setcap "cap_net_bind_service=+ep" "$py" >>"$LOG" 2>&1; then
    ok "setcap applied to: ${CYAN}${py}${RESET}"
    return 0
  fi
  if [[ "$real" != "$py" ]]; then
    if sudo setcap "cap_net_bind_service=+ep" "$real" >>"$LOG" 2>&1; then
      ok "setcap applied to resolved python: ${CYAN}${real}${RESET}"
      return 0
    fi
  fi

  warn "setcap failed (filesystem/permissions may block file capabilities)."
  return 1
}

verify_setcap() {
  local py="$1"
  local real
  real="$(readlink -f "$py" 2>/dev/null || echo "$py")"
  if have getcap; then
    if getcap "$py" 2>/dev/null | grep -qi cap_net_bind_service; then return 0; fi
    if [[ "$real" != "$py" ]] && getcap "$real" 2>/dev/null | grep -qi cap_net_bind_service; then return 0; fi
  fi
  return 1
}

if verify_setcap "$VENV_PY"; then
  ok "CAP_NET_BIND_SERVICE already present (skipping)."
else
  if apply_setcap "$VENV_PY" && verify_setcap "$VENV_PY"; then
    ok "Low-port permission fix applied (setcap)."
    warn "To revert later: ${CYAN}sudo setcap -r \"$(readlink -f "$VENV_PY")\"${RESET}"
  else
    # LAST RESORT to prevent instant churn: lower unprivileged port start
    warn "Fallback: enabling unprivileged low ports via sysctl (system-wide)."
    SYSCTL_FILE="/etc/sysctl.d/99-webverse-unprivileged-ports.conf"
    run "Writing sysctl config: ${CYAN}${SYSCTL_FILE}${RESET}" \
      sudo bash -lc "printf 'net.ipv4.ip_unprivileged_port_start=0\n' > '$SYSCTL_FILE'"
    run "Applying sysctl settings" sudo sysctl --system
    warn "To revert later: ${CYAN}sudo rm -f '$SYSCTL_FILE' && sudo sysctl -w net.ipv4.ip_unprivileged_port_start=1024${RESET}"
  fi
fi

# ---------- final notes ----------
say "Done."
info "Next steps (recommended):"
warn "1) Log out/in (or reboot) so docker group + PATH updates apply cleanly."
warn "2) Then run: ${CYAN}webverse${RESET}"
warn "If anything fails, paste: ${CYAN}tail -n 120 \"$LOG\"${RESET}"

