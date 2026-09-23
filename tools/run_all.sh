#!/bin/sh
# SCW build + test + end-to-end examples (macOS, offline, stdlib only).
# Exact run command (from the repo root):
#   sh tools/run_all.sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH=src

echo "=== 1. rule-pack gate (S1-S7 + engine compatibility) ==="
python3 -m scw check-pack --pack packs/scw-qatar-starter.v0.1.0.json

echo "=== 2. test suite (41 checks, A1-A12 + A13 quote contract + A14 offsets + A15 labels) ==="
python3 tests/test_scw.py

echo "=== 2b. JS/Python engine parity (5 vectors, canonical-identical) ==="
node tests/parity.js

echo "=== 3. end-to-end runs (pinned clocks => byte-reproducible) ==="
python3 -m scw run --pack packs/scw-qatar-starter.v0.1.0.json \
  --input tests/fixtures/case-input-guided.fixture.json \
  --outdir runs/golden-guided --run-started 2026-09-22T22:10:00Z
python3 -m scw run --pack packs/scw-qatar-starter.v0.1.0.json \
  --input tests/fixtures/case-input-freetext.fixture.json \
  --outdir runs/golden-freetext --run-started 2026-09-22T22:12:00Z
python3 -m scw run --pack packs/scw-qatar-starter.v0.1.0.json \
  --input examples/ex-ijara-guided.json \
  --outdir runs/ex-ijara-guided --run-started 2026-09-22T23:00:00Z
python3 -m scw run --pack packs/scw-qatar-starter.v0.1.0.json \
  --input examples/ex-murabaha-interest-freetext.json \
  --outdir runs/ex-murabaha-interest --run-started 2026-09-22T23:01:00Z
python3 -m scw run --pack packs/scw-qatar-starter.v0.1.0.json \
  --input examples/ex-takaful-mixed-freetext.json \
  --outdir runs/ex-takaful-mixed --run-started 2026-09-22T23:02:00Z

echo "=== 4. export hashes ==="
shasum -a 256 runs/*/export.* runs/*/case-result.json runs/*/run-attestation.json
echo "ALL DONE"
