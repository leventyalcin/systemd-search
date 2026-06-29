#!/bin/bash
# Runs inside the target Debian container.
# Usage: build-deb.sh <target> <version>   e.g. build-deb.sh debian12 1.2.0
set -euo pipefail

TARGET=${1:?Usage: build-deb.sh <target> <version>}
VERSION=${2:?Usage: build-deb.sh <target> <version>}
# Debian uses ~ as the pre-release separator (sorts before the bare release).
DEB_VERSION="${VERSION//-/\~}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends python3 -qq

PKG_ROOT=/build/systemd-search
mkdir -p "${PKG_ROOT}/DEBIAN" "${PKG_ROOT}/usr/bin"

cp /workspace/systemd-search "${PKG_ROOT}/usr/bin/systemd-search"
chmod 755 "${PKG_ROOT}/usr/bin/systemd-search"

cat > "${PKG_ROOT}/DEBIAN/control" << EOF
Package: systemd-search
Version: ${DEB_VERSION}
Architecture: all
Maintainer: systemd-search contributors <noreply@github.com>
Depends: python3
Description: Query systemd units by custom section labels
 CLI tool to filter and query systemd units by custom section labels
 defined in X- sections (e.g. [X-Labels]). Handles drop-in overrides
 via systemctl cat. Supports filtering by label key/value, unit type,
 and enabled/active state.
EOF

DEST="/workspace/systemd-search-${VERSION}-${TARGET}.all.deb"
dpkg-deb --build "${PKG_ROOT}" "$DEST"
echo "Built: $DEST"
