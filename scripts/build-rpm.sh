#!/bin/bash
# Runs inside the target Rocky/RHEL container.
# Usage: build-rpm.sh <target> <version>   e.g. build-rpm.sh rocky9 1.2.0
set -euo pipefail

TARGET=${1:?Usage: build-rpm.sh <target> <version>}
VERSION=${2:?Usage: build-rpm.sh <target> <version>}

dnf install -y rpm-build python3 --quiet --setopt=install_weak_deps=False

mkdir -p /root/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

cat > /root/rpmbuild/SPECS/systemd-search.spec << EOF
Name:           systemd-search
Version:        ${VERSION}
Release:        1%{?dist}
Summary:        Query systemd units by custom section labels
License:        MIT
BuildArch:      noarch
Requires:       python3

%description
CLI tool to filter and query systemd units by custom section labels
defined in X- sections (e.g. [X-Labels]). Handles drop-in overrides
via systemctl cat. Supports filtering by label key/value, unit type,
and enabled/active state.

%install
mkdir -p %{buildroot}%{_bindir}
install -m 0755 /workspace/systemd-search %{buildroot}%{_bindir}/systemd-search

%files
%{_bindir}/systemd-search

%changelog
* $(date '+%a %b %d %Y') CI Build <noreply@github.com> - ${VERSION}-1
- Automated package build
EOF

rpmbuild -bb /root/rpmbuild/SPECS/systemd-search.spec

RPM=$(find /root/rpmbuild/RPMS/noarch -name "*.rpm" | head -1)
DEST="/workspace/systemd-search-${VERSION}-${TARGET}.noarch.rpm"
cp "$RPM" "$DEST"
echo "Built: $DEST"
