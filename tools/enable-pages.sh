#!/bin/sh
# SCW GitHub Pages enabler.
# One command: points GitHub Pages at docs/ on main and prints the public URL.
# The repository is public by owner decision and Pages serves docs/ on main.
#
# Usage:  sh tools/enable-pages.sh
set -eu
cd "$(dirname "$0")/.."
REPO="ahrazzle/sharia-docs"
sh tools/build_site.sh
git status --porcelain -- docs/ | grep -q . \
  && { echo "docs/ has uncommitted changes — commit and push first"; exit 1; }
gh api "repos/${REPO}/pages" -X POST \
  -f 'source[branch]=main' -f 'source[path]=/docs' --jq '{url: .html_url}' \
  || gh api "repos/${REPO}/pages" -X PUT \
  -f 'source[branch]=main' -f 'source[path]=/docs' --jq '{url: .html_url}'
echo "Published: https://ahrazzle.github.io/sharia-docs/ (allow ~1 min to build)"
