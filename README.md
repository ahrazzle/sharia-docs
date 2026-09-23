# Sharia-Compliance Workbook MVP (Qatar)

Repo: `ahrazzle/sharia-docs` (public by owner decision).
Live workbook: https://ahrazzle.github.io/sharia-docs/ (Pages serves `docs/`
on `main`).

Deterministic offline workbook: a versioned rule pack, a pure-function rule
engine, a mapping worksheet, and single-run attestation exports (JSON / CSV /
print-ready HTML). Built against a locked architecture contract (schemas,
engine semantics, citation quote contract), a locked UX contract (worksheet
layout, standing labels, no-default guided flow), and a research correction
brief (citation provenance fixes); the starter rule pack ships as-is at
v0.2.0 draft, pending human review.

**Drafting aid only — not legal advice, not a fatwa, not regulatory approval.**
Every verdict is a *proposed* worksheet field pending human review and sign-off.
`non_compliant` (Gap) is unreachable in pack v0.2.0 by design: no verified
sharia-substantive source exists yet, so Gap verdicts are withheld, not guessed.
Every export carries the standing label `Input status: unconfirmed input`.

## Run (macOS, offline, stdlib only — no third-party packages, no network)

```sh
sh tools/run_all.sh
```

That runs: pack gate (S1–S7 + engine compatibility) → 41-test suite →
JS/Python parity gate → five end-to-end runs (two golden fixtures + three
worked examples, pinned clocks so reruns are byte-identical) → export hashes.

Single run:

```sh
export PYTHONPATH=src
python3 -m scw check-pack --pack packs/scw-qatar-starter.v0.1.0.json
python3 -m scw run --pack packs/scw-qatar-starter.v0.1.0.json \
  --input examples/ex-ijara-guided.json --outdir runs/my-run \
  --run-started 2026-09-22T23:00:00Z
```

Local browser workbook (double-click, no server, no network):

```sh
open app/index.html
```

Headless DOM evidence (Playwright-cached Chromium over CDP, stdlib only):

```sh
python3 tools/dom_evidence.py   # 11/11 checks, evidence/dom-evidence.json + dom.png
```

Static site output (Pages-ready):

```sh
sh tools/build_site.sh   # copies app/ shell into docs/ + .nojekyll
```

## Layout

- `schemas/` — four LOCKED JSON Schemas (the normative interfaces),
  rule-pack schema at v1.1.0 (citation `quote` + `quote_sha256` contract).
- `packs/scw-qatar-starter.v0.1.0.json` — starter rule pack
  (`scw-qatar-starter` v0.2.0 draft, pending human review; 4 domains, 10 lexicon terms,
  12 citations = 0 verified + 12 unverified, 9 rules, **0 blocking rules**).
  Canonical sha256 `1ea71e863f05f7b8c1c2fd64ce0b58fd03de5a3512e25b15d4bee64451cae042`.
- `src/scw/` — engine (`engine.py`, pure `evaluate`), attestation
  (`attest.py`), CSV + print-ready HTML exports (`exports.py`), stdlib-only
  structural gates (`lite.py`), CLI (`cli.py`). Engine version `1.0.0`
  (satisfies the pack's `engine_min_version`); golden vectors are reproduced
  through the reference-vector identity `0.1.0` (architecture decision D10).
- `app/` — offline workbook UI (`index.html` + `scw-engine.js`, zero external
  resources): intake (paste + guided), four panes (structure reading, mapping
  worksheet, attestation pack, unverified list), UI-session confirmations,
  human-only recorded verdicts, client-side JSON/CSV/HTML export, print CSS.
  The JS engine is byte-parity-proven against Python (`tests/parity.js`).
- `docs/` — generated static-site copy of `app/` (see Pages note); do not
  hand-edit, regenerate with `sh tools/build_site.sh`.
- `tests/` — `test_scw.py` (41 checks: A1–A12 proof obligations + A13 quote
  contract + A14 single-offset-space + A15 labels) + `parity.js`;
  `tests/fixtures/` — the locked golden input/result/attestation vectors.
- `examples/` — three worked inputs (ijara guided, murabaha-mislabelled
  interest-bearing loan, bilingual takaful/gharar free text).
- `runs/` — the five end-to-end runs with all exports + hashes.
- `evidence/` — headless DOM evidence for the browser launch.
- `tools/` — `run_all.sh`, `dom_evidence.py`, `inject_pack.py`,
  `build_site.sh`, `enable-pages.sh`.

## Pages (live)

`docs/` holds the servable workbook shell with the drafting-aid disclaimer in
the static footer of the first screen. Pages serves `docs/` on `main` at
https://ahrazzle.github.io/sharia-docs/ — enabled under the owner's recorded
authorization. To re-run the enablement (idempotent):

```sh
sh tools/enable-pages.sh   # configures Pages source, prints the URL
```

The public release surface is the Pages site above, enabled under the
owner's recorded authorization; nothing on it claims verification that an
independent QA gate has not confirmed — the unverified rows stay unverified.

## Coverage limits (substance-verbatim; also in every HTML export)

1. The pack covers murabaha, ijara, takaful and related structures across four
   domains. Anything outside the lexicon is "not covered" — never "compliant
   by silence". 2. Free-text matching is exact-surface only — no stemming, no
   Arabic morphology. 3. Unmatched free-text content is NOT assessed.
4. "compliant" is an absence state, not an affirmative ruling.
5. "non_compliant" is unreachable until a blocking rule ships with fetched,
   hashed primary sources. 6. Runs are single-run and stateless.
7. Timestamps are local wall clock — provenance only. 8. Drafting aid; not
   legal or sharia advice.

## Fences (locked)

No invented citations/article numbers (missing article data renders "not
stated in pack"); no schema/interface changes beyond the locked v1.1.0
quote contract; zero network calls at runtime (structurally gated: no
network/model imports in `src/scw`, proven by test); public release surface is
the Pages site only (enabled under owner authorization, nothing claims an
unconfirmed gate); no
auto-signoff (sign-off is schema-const blank, no code path fills it); no
credentials or telemetry.
