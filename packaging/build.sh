#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Builds KaramTC packages into packaging/dist/:
#   - karamtc_<ver>_all.deb                  (Debian/Ubuntu — needs dpkg-deb)
#   - karamtc-<ver>-1.noarch.rpm              (Fedora/RHEL/openSUSE — needs rpmbuild)
#   - karamtc-<ver>-1-any.pkg.tar.zst          (Arch — needs makepkg; built by
#                                               packaging/build-arch.sh)
#
# Unlike a from-source pip install, all three packages declare PyMuPDF,
# Pillow, and PyGObject as native system-package dependencies (python3-fitz
# / python3-pil on Debian, python3-PyMuPDF / python3-pillow on Fedora,
# python-pymupdf / python-pillow on Arch), so installing the built package
# needs no internet access and no venv/pip step at all.
#
# Run this ON the distro you're packaging for. dpkg-deb ships with
# dpkg-dev on any Debian/Ubuntu-family system; rpmbuild ships with the
# rpm-build package on Fedora/RHEL (and works on openSUSE too); makepkg is
# Arch-specific tooling (ships with base-devel) and isn't realistically
# installable elsewhere. Whichever of the three tools are present, this
# script builds just those — so it's safe to run as-is on any of them.
#
# Extra makepkg options can be passed with MAKEPKG_FLAGS (e.g. MAKEPKG_FLAGS=-s to
# install missing dependencies with pacman first). The Arch package is built by
# packaging/build-arch.sh, which you can also run on its own.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$PROJECT_ROOT/packaging/work"
OUT_DIR="$PROJECT_ROOT/packaging/dist"
VERSION="$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$PROJECT_ROOT/src/config.py")"
APP_ID="io.github.AbuKaram01.KaramTC"
MAINTAINER="AbuKaram01 <AbuKaram01@users.noreply.github.com>"

[ -n "$VERSION" ] || { echo "Could not read the version from src/config.py." >&2; exit 1; }

info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
ok()   { printf '\033[1;32m\xE2\x9C\x93\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$1"; }

HAVE_DEB=0;  command -v dpkg-deb >/dev/null 2>&1 && HAVE_DEB=1
HAVE_RPM=0;  command -v rpmbuild >/dev/null 2>&1 && HAVE_RPM=1
HAVE_ARCH=0; command -v makepkg  >/dev/null 2>&1 && HAVE_ARCH=1

if [ "$HAVE_DEB" -eq 0 ] && [ "$HAVE_RPM" -eq 0 ] && [ "$HAVE_ARCH" -eq 0 ]; then
    echo "None of dpkg-deb, rpmbuild, or makepkg found." >&2
    echo "Install dpkg-dev to build the .deb (any Debian/Ubuntu system)," >&2
    echo "rpm-build to build the .rpm (Fedora/RHEL/openSUSE)," >&2
    echo "or run this script on Arch, where makepkg ships with base-devel." >&2
    exit 1
fi

# Clean only what this script produces, so a package built by build-arch.sh survives.
rm -rf "$WORK_DIR/deb-root" "$WORK_DIR/rpm-root" "$WORK_DIR/rpmbuild" "$WORK_DIR/rpmdb" \
       "$WORK_DIR/karamtc.spec" "$WORK_DIR/rpmbuild.log"
mkdir -p "$WORK_DIR" "$OUT_DIR"
rm -f "$OUT_DIR"/karamtc_*_all.deb "$OUT_DIR"/karamtc_*_amd64.deb "$OUT_DIR"/karamtc-*.noarch.rpm

# ==== .deb ===================================================================
if [ "$HAVE_DEB" -eq 1 ]; then
    info "Building karamtc_${VERSION}_all.deb..."
    deb_root="$WORK_DIR/deb-root"
    payload="$deb_root/opt/karamtc"
    mkdir -p "$payload" "$deb_root/usr/bin" "$deb_root/usr/share/applications" \
             "$deb_root/usr/share/icons/hicolor/scalable/apps" "$deb_root/DEBIAN"

    cp -r "$PROJECT_ROOT/src/main.py" "$PROJECT_ROOT/src/config.py" "$PROJECT_ROOT/src/settings.py" \
          "$PROJECT_ROOT/src/core" "$PROJECT_ROOT/src/providers" "$PROJECT_ROOT/src/ui" \
          "$payload/"
    find "$payload" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

    cp "$PROJECT_ROOT/data/icons/hicolor/scalable/apps/${APP_ID}.svg" \
        "$deb_root/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"

    cat > "$deb_root/usr/bin/karamtc" << 'LAUNCHER'
#!/bin/sh
# Fixed path — this package always installs to /opt/karamtc.
# PYTHONDONTWRITEBYTECODE keeps that install-tree read-only at runtime
# (no __pycache__ written under /opt, which apt/dpkg doesn't track and
# would otherwise be left behind — or fail outright — on removal).
export PYTHONDONTWRITEBYTECODE=1
exec python3 /opt/karamtc/main.py "$@"
LAUNCHER
    chmod 755 "$deb_root/usr/bin/karamtc"

    sed "s|^Exec=karamtc-exec-placeholder|Exec=karamtc|" \
        "$PROJECT_ROOT/data/${APP_ID}.desktop" \
        > "$deb_root/usr/share/applications/${APP_ID}.desktop"

    cat > "$deb_root/DEBIAN/control" << CONTROL
Package: karamtc
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.5), python3-fitz, python3-pil, tesseract-ocr, tesseract-ocr-ara, tesseract-ocr-eng
Recommends: hicolor-icon-theme
Suggests: python3-pip
Maintainer: $MAINTAINER
Description: Copy text out of images and PDFs (Karam Text Copier)
 A GTK4 + libadwaita desktop app for extracting text from images (JPEG,
 PNG, WebP) and PDFs, with hybrid direct-text/OCR extraction and
 resumable, cancellable extraction for large scanned books. Fully
 offline — no dependencies are downloaded or compiled at install time.
CONTROL

    cat > "$deb_root/DEBIAN/postinst" << 'POSTINST'
#!/bin/sh
set -e
# Makes the app icon show up immediately instead of only after the next
# unrelated package triggers a cache rebuild (or a logout/login).
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
POSTINST
    chmod 755 "$deb_root/DEBIAN/postinst"

    cat > "$deb_root/DEBIAN/postrm" << 'POSTRM'
#!/bin/sh
set -e
# Safety net for anything written under /opt/karamtc at runtime that
# dpkg never tracked (shouldn't happen with PYTHONDONTWRITEBYTECODE set,
# but this guarantees a clean removal either way).
if [ "$1" = "purge" ] || [ "$1" = "remove" ]; then
    rm -rf /opt/karamtc
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
POSTRM
    chmod 755 "$deb_root/DEBIAN/postrm"

    dpkg-deb --build --root-owner-group "$deb_root" "$OUT_DIR/karamtc_${VERSION}_all.deb" >/dev/null
    ok "karamtc_${VERSION}_all.deb"
else
    warn "dpkg-deb not found — skipping .deb (install dpkg-dev to build it)."
fi

# ==== .rpm ===================================================================
if [ "$HAVE_RPM" -eq 1 ]; then
    info "Building karamtc-${VERSION}-1.noarch.rpm..."
    rpm_root="$WORK_DIR/rpm-root"
    payload="$rpm_root/opt/karamtc"
    mkdir -p "$payload" "$rpm_root/usr/bin" "$rpm_root/usr/share/applications" \
             "$rpm_root/usr/share/icons/hicolor/scalable/apps"

    cp -r "$PROJECT_ROOT/src/main.py" "$PROJECT_ROOT/src/config.py" "$PROJECT_ROOT/src/settings.py" \
          "$PROJECT_ROOT/src/core" "$PROJECT_ROOT/src/providers" "$PROJECT_ROOT/src/ui" \
          "$payload/"
    find "$payload" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

    cp "$PROJECT_ROOT/data/icons/hicolor/scalable/apps/${APP_ID}.svg" \
        "$rpm_root/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"

    cat > "$rpm_root/usr/bin/karamtc" << 'LAUNCHER'
#!/bin/sh
# Fixed path — this package always installs to /opt/karamtc.
# PYTHONDONTWRITEBYTECODE keeps that install-tree read-only at runtime
# (no __pycache__ written under /opt, which rpm/dnf doesn't track and
# would otherwise be left behind — or fail outright — on removal).
export PYTHONDONTWRITEBYTECODE=1
exec python3 /opt/karamtc/main.py "$@"
LAUNCHER
    chmod 755 "$rpm_root/usr/bin/karamtc"

    sed "s|^Exec=karamtc-exec-placeholder|Exec=karamtc|" \
        "$PROJECT_ROOT/data/${APP_ID}.desktop" \
        > "$rpm_root/usr/share/applications/${APP_ID}.desktop"

    # Package names verified against Fedora's actual repos rather than
    # assumed — python3-PyMuPDF, python3-gobject, gtk4, and libadwaita are
    # all real, current Fedora package names (unlike Debian's python3-fitz,
    # Fedora's PyMuPDF package keeps the project's own capitalization).
    mkdir -p "$WORK_DIR/rpmbuild"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    cat > "$WORK_DIR/karamtc.spec" << SPEC
Name:           karamtc
Version:        $VERSION
Release:        1%{?dist}
Summary:        Copy text out of images and PDFs (Karam Text Copier)
License:        AGPL-3.0-or-later
URL:            https://github.com/AbuKaram01/KaramTC
BuildArch:      noarch
# Every real runtime dependency is already declared by hand below, so
# rpmbuild's automatic dependency scanner (which would otherwise inspect each
# payload file, including the shebang of /usr/bin/karamtc) is switched off.
# Note: this does not stop rpmbuild from opening the system RPM database on a
# non-RPM-native distro; that is handled by the rpmbuild flags further down.
AutoReqProv:    no

Requires:       python3 >= 3.10
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita >= 1.5
Requires:       python3-PyMuPDF
Requires:       python3-pillow
Requires:       tesseract
Requires:       tesseract-langpack-ara
Requires:       tesseract-langpack-eng
Requires:       tesseract-osd
Recommends:     hicolor-icon-theme
Suggests:       python3-pip

%description
A GTK4 + libadwaita desktop app for extracting text from images (JPEG,
PNG, WebP) and PDFs, with hybrid direct-text/OCR extraction and
resumable, cancellable extraction for large scanned books. Fully
offline — no dependencies are downloaded or compiled at install time.

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -a ${rpm_root}/. %{buildroot}/

%files
/opt/karamtc
/usr/bin/karamtc
/usr/share/applications/${APP_ID}.desktop
/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg

%post
gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || :

%postun
# \$1 is the count of this package's installs remaining after the
# operation — 0 means a full removal, not an upgrade in progress.
if [ "\$1" = "0" ]; then
    rm -rf /opt/karamtc
fi
gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || :
SPEC

    # Two flags keep rpmbuild away from the machine's own RPM database, which
    # on Debian/Ubuntu (rpmbuild installed only to build this) is root-owned and
    # unreadable for a normal user. That is what used to print
    # "Unable to open sqlite database /var/lib/rpm/rpmdb.sqlite" on a build that
    # then succeeded anyway:
    #   --nodeps          this spec has no BuildRequires, so there is nothing to
    #                     verify; skipping the check skips the database access.
    #   _dbpath (private) any remaining database access goes to a throwaway
    #                     directory inside the work dir instead of /var/lib/rpm.
    # Output goes to a log and is only shown if the build fails: rpmbuild traces
    # every build-script command ("+ cd ...") to stderr, which is just noise.
    rpm_log="$WORK_DIR/rpmbuild.log"
    mkdir -p "$WORK_DIR/rpmdb"
    if rpmbuild --nodeps \
                --define "_dbpath $WORK_DIR/rpmdb" \
                --define "_topdir $WORK_DIR/rpmbuild" \
                -bb "$WORK_DIR/karamtc.spec" >"$rpm_log" 2>&1; then
        find "$WORK_DIR/rpmbuild/RPMS" -name "*.rpm" -exec mv {} "$OUT_DIR/" \;
        ok "karamtc-${VERSION}-1.noarch.rpm"
    else
        cat "$rpm_log" >&2
        warn "rpmbuild failed — its output is shown above. The .deb above (if built) is unaffected."
    fi
else
    warn "rpmbuild not found — skipping .rpm (install rpm-build: 'sudo dnf install rpm-build' on Fedora/RHEL, 'sudo zypper install rpm-build' on openSUSE)."
fi

# ==== Arch (.pkg.tar.zst) ====================================================
# build-arch.sh makes the source tarball from this checkout and runs makepkg on
# packaging/arch/PKGBUILD, leaving the result in packaging/dist.
if [ "$HAVE_ARCH" -eq 1 ]; then
    if [ "$EUID" -eq 0 ]; then
        warn "makepkg refuses to run as root — skipping the Arch package. Re-run this script as a normal user to build it."
    else
        info "Building the Arch package (packaging/build-arch.sh)..."
        # shellcheck disable=SC2086  # MAKEPKG_FLAGS is meant to word-split
        if "$PROJECT_ROOT/packaging/build-arch.sh" --noconfirm ${MAKEPKG_FLAGS:-}; then
            ok "Arch package built."
        else
            warn "build-arch.sh failed (see its output above) — the other packages are unaffected."
        fi
    fi
else
    warn "makepkg not found — skipping the Arch package. It's Arch-specific tooling (ships with base-devel); build it on an Arch machine, either by running this script there or with ./packaging/build-arch.sh."
fi

echo
ok "Done. Output in: $OUT_DIR"
ls -la "$OUT_DIR" 2>/dev/null || true
