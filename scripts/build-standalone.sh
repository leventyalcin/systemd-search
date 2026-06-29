#!/bin/bash
# Builds a self-contained Python zipapp executable from the installed package.
# The output file runs on any host with Python 3.9+ and no package installation.
# Usage: build-standalone.sh <version>   e.g. build-standalone.sh 1.2.0
set -euo pipefail

VERSION=${1:?Usage: build-standalone.sh <version>}

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# Install the package and its (stdlib-only) deps into the staging dir
pip install . --target "$STAGE" --quiet

# Entry point: import from the installed package
cat > "$STAGE/__main__.py" << 'EOF'
from systemd_search import main
main()
EOF

DEST="systemd-search-${VERSION}"
python3 -m zipapp "$STAGE" --output "$DEST" --python '/usr/bin/env python3'
chmod +x "$DEST"
echo "Built: $DEST"
