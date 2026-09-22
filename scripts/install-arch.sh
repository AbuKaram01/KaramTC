#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# One-command installer for KaramTC on Arch-based systems (Arch, Manjaro, EndeavourOS...),
# from a git checkout — installs into your own $HOME, like scripts/install-debian.sh.
# Run from anywhere:  ./scripts/install-arch.sh
#
# Prefer a real package? Build one with packaging/build-arch.sh.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

APP_ID="io.github.AbuKaram01.KaramTC"
REQUIRED_PYTHON="3.10"

info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$1"; }
fail() { printf '\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

for argument in "$@"; do
    case "$argument" in
        -h|--help)
            echo "Usage: ./scripts/install-arch.sh"
            echo "  Installs KaramTC from this checkout into .venv and adds a launcher to your applications menu."
            exit 0
            ;;
        *) fail "Unknown option: $argument (try --help)" ;;
    esac
done

if ! command -v pacman >/dev/null 2>&1; then
    fail "This script is for Arch-based systems (needs pacman). Not found on this machine — on Debian/Ubuntu use scripts/install-debian.sh."
fi

if [ "$EUID" -eq 0 ]; then
    fail "Don't run this as root — it installs into your own \$HOME. Run it as your normal user; it will ask for sudo only for the system packages."
fi

PACKAGES=(
    python python-pip python-gobject gtk4 libadwaita librsvg adwaita-icon-theme
    tesseract tesseract-data-eng tesseract-data-ara tesseract-data-osd
)

info "Installing system packages (GTK4, libadwaita, Python bindings, Tesseract)..."
# --needed: skip what is already installed (and don't reinstall it).
sudo pacman -S --needed --noconfirm "${PACKAGES[@]}"
ok "System packages installed."

PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$(printf '%s\n' "$REQUIRED_PYTHON" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_PYTHON" ]; then
    fail "Python $REQUIRED_PYTHON+ is required — found $PYTHON_VERSION. This isn't KaramTC's own \
requirement (its code has no 3.10-only syntax) — it's PyMuPDF's, KaramTC's PDF library dependency, \
which only ships wheels for 3.10+ now."
fi
ok "Python $PYTHON_VERSION OK."

# Arch is a rolling release: if Python has moved to a new minor version since .venv was
# created, that .venv no longer works — start it over rather than reuse it.
if [ -d .venv ]; then
    VENV_VERSION="$(sed -n 's/^version[[:space:]]*=[[:space:]]*\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' .venv/pyvenv.cfg 2>/dev/null | head -n 1)"
    if [ "$VENV_VERSION" != "$PYTHON_VERSION" ]; then
        info "The existing .venv was made with Python ${VENV_VERSION:-?}, the system now has $PYTHON_VERSION — recreating it."
        rm -rf .venv
    fi
fi

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
# The launcher's Exec needs an absolute path: the .venv's python isn't on the system PATH,
# and a desktop entry whose Exec can't be resolved is silently not registered at all.
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
echo "with: sudo pacman -S tesseract-data-<lang>"
echo "(see https://tesseract-ocr.github.io/tessdoc/Data-Files.html for codes)"
echo
echo "Note: after an Arch update moves Python to a new minor version, re-run this"
echo "script once to rebuild .venv."
