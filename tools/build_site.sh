#!/bin/sh
# SCW static-site builder (Pages-ready requirement).
# Regenerates docs/ as a verbatim copy of the offline workbook shell in app/.
# Never hand-edit docs/: fix app/ and re-run this script.
# Exact run command (from the repo root):
#   sh tools/build_site.sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p docs
cp app/index.html docs/index.html
cp app/scw-engine.js docs/scw-engine.js
touch docs/.nojekyll
echo "site bytes: index.html=$(wc -c < docs/index.html) scw-engine.js=$(wc -c < docs/scw-engine.js)"
echo "disclaimer present: $(grep -c 'Drafting aid only' docs/index.html)x"
echo "docs/ regenerated and in sync with app/ (Pages serves docs/ on main)"
