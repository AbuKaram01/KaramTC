#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# One-command installer for KaramTC on Debian/Ubuntu-based systems.
# Run from anywhere:  ./scripts/install-debian.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

APP_ID="io.github.AbuKaram01.KaramTC"
REQUIRED_PYTHON="3.10"

info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
ok()   { printf '\033[1;32m\xE2\x9C\x93\033[0m %s\n' "$1"; }
fail() { printf '\033[1;31m\xE2\x9C\x97 %s\033[0m\n' "$1" >&2; exit 1; }

if ! command -v apt >/dev/null 2>&1; then
    fail "This script is for Debian/Ubuntu-based systems (needs apt). Not found on this machine."
fi

if [ "$EUID" -eq 0 ]; then
    fail "Don't run this as root — it installs into your own \$HOME. Run it as your normal user; it will ask for sudo only for the system packages."
fi

info "Installing system packages (GTK4, libadwaita, Python bindings, Tesseract)..."
sudo apt update -qq
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-venv python3-dev \
    tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng
ok "System packages installed."

# The UI uses libadwaita's dialog widgets (Adw.PreferencesDialog and friends),
# added in 1.5 — Debian 12 and Ubuntu 22.04 ship older versions, where the app
# would install fine and then fail to start.
REQUIRED_ADW="1.5"
ADW_VERSION="$(dpkg-query -W -f='${Version}' gir1.2-adw-1 2>/dev/null || true)"
if [ -z "$ADW_VERSION" ] || ! dpkg --compare-versions "$ADW_VERSION" ge "$REQUIRED_ADW"; then
    fail "KaramTC needs libadwaita $REQUIRED_ADW or newer, but this system has ${ADW_VERSION:-none}. Use a newer release (Debian 13 / Ubuntu 24.04 or later)."
fi
ok "libadwaita $ADW_VERSION OK."

PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$(printf '%s\n' "$REQUIRED_PYTHON" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_PYTHON" ]; then
    fail "Python $REQUIRED_PYTHON+ is required — found $PYTHON_VERSION. This isn't KaramTC's own \
requirement (its code has no 3.10-only syntax) — it's PyMuPDF's, KaramTC's PDF library dependency, \
which dropped Python 3.9 support in late 2025 and only ships wheels for 3.10+ now. Upgrading your \
system Python (or your distro) is the straightforward fix; pinning an older PyMuPDF release in \
requirements.txt is possible but trades away its more recent fixes."
fi
ok "Python $PYTHON_VERSION OK."

if [ ! -d .venv ]; then
    info "Creating virtual environment (.venv)..."
    python3 -m venv --system-site-packages .venv
    ok "Virtual environment created."
else
    info "Reusing existing .venv"
fi

info "Installing Python dependencies (PyMuPDF, Pillow, faster-whisper)..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
ok "Python dependencies installed."

info "Installing the desktop launcher and app icon for your user..."
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
# GIO refuses to even register a desktop entry whose Exec command can't be
# resolved on PATH — and our venv's python isn't on PATH unless activated,
# so a plain copy of the template silently fails to appear anywhere (search,
# app grid, gtk-launch — all of it, with no error). The absolute path to the
# venv's own python always resolves regardless of PATH.
sed "s|^Exec=karamtc-exec-placeholder|Exec=${PROJECT_ROOT}/.venv/bin/python3 ${PROJECT_ROOT}/src/main.py|" \
    "data/${APP_ID}.desktop" > ~/.local/share/applications/"${APP_ID}.desktop"
cp "data/icons/hicolor/scalable/apps/${APP_ID}.svg" \
    ~/.local/share/icons/hicolor/scalable/apps/"${APP_ID}.svg"
gtk-update-icon-cache -q -t -f ~/.local/share/icons/hicolor >/dev/null 2>&1 || true
ok "Desktop launcher and app icon installed."

echo
ok "KaramTC is installed."
echo
echo "  Run it with:"
echo "    ${PROJECT_ROOT}/.venv/bin/python3 ${PROJECT_ROOT}/src/main.py"
echo
echo "  Or activate the virtual environment first:"
echo "    source ${PROJECT_ROOT}/.venv/bin/activate"
echo "    python3 src/main.py"
echo
echo "  It should also now appear in your applications menu as \"KaramTC\"."
echo
echo "Only English and Arabic language data were installed above — add more"
echo "with: sudo apt install tesseract-ocr-<lang>"
echo "(see https://tesseract-ocr.github.io/tessdoc/Data-Files.html for codes)"
