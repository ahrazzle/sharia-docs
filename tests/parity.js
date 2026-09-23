#!/usr/bin/env node
/* SCW engine parity gate: the JS port in
 * app/scw-engine.js must produce canonical-identical case results to the
 * Python engine on every golden and worked-example vector. Exit 0 = parity.
 * Usage: node tests/parity.js  (from the repo root)
 */
"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const BASE = path.dirname(path.dirname(path.resolve(__filename)));
const eng = require(path.join(BASE, "app", "scw-engine.js"));

function canonHash(obj) {
  return crypto.createHash("sha256")
    .update(eng.scwCanonString(obj), "utf8").digest("hex");
}

const pack = JSON.parse(fs.readFileSync(
  path.join(BASE, "packs", "scw-qatar-starter.v0.1.0.json"), "utf8"));
const packSha = canonHash(pack);
if (packSha !== "1ea71e863f05f7b8c1c2fd64ce0b58fd03de5a3512e25b15d4bee64451cae042") {
  console.error("FAIL pack identity " + packSha);
  process.exit(1);
}

const cases = [
  ["tests/fixtures/case-input-guided.fixture.json",
   "tests/fixtures/case-result-guided.fixture.json", "0.1.0"],
  ["tests/fixtures/case-input-freetext.fixture.json",
   "tests/fixtures/case-result-freetext.fixture.json", "0.1.0"],
  ["examples/ex-ijara-guided.json",
   "runs/ex-ijara-guided/case-result.json", "1.0.0"],
  ["examples/ex-murabaha-interest-freetext.json",
   "runs/ex-murabaha-interest/case-result.json", "1.0.0"],
  ["examples/ex-takaful-mixed-freetext.json",
   "runs/ex-takaful-mixed/case-result.json", "1.0.0"]
];

let fail = 0;
function expectSha(label, got, want) {
  if (got === want) { console.log("PASS sha " + label); }
  else { console.error("FAIL sha " + label + " got=" + got); fail++; }
}
expectSha("abc", eng.scwSha256Hex(eng.scwUtf8("abc")),
  "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
expectSha("empty", eng.scwSha256Hex(eng.scwUtf8("")),
  "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
expectSha("pack-canon", eng.scwSha256Hex(eng.scwUtf8(
  eng.scwCanonString(pack))), packSha);
for (const [inRel, expRel, engVer] of cases) {
  const inp = JSON.parse(fs.readFileSync(path.join(BASE, inRel), "utf8"));
  const exp = JSON.parse(fs.readFileSync(path.join(BASE, expRel), "utf8"));
  let got;
  try {
    got = eng.scwEvaluate(inp, pack, packSha, engVer);
  } catch (e) {
    console.error("FAIL " + inRel + " threw: " + e.message);
    fail++;
    continue;
  }
  const a = eng.scwCanonString(got), b = eng.scwCanonString(exp);
  if (a === b) {
    console.log("PASS " + inRel + " canonical-identical sha=" +
      crypto.createHash("sha256").update(a, "utf8").digest("hex"));
    // CSV byte-parity against the Python-built run artifacts, where present
    const runDir = { "examples/ex-ijara-guided.json": "runs/ex-ijara-guided",
      "examples/ex-murabaha-interest-freetext.json":
      "runs/ex-murabaha-interest",
      "examples/ex-takaful-mixed-freetext.json": "runs/ex-takaful-mixed" }[inRel];
    if (runDir) {
      const files = fs.readdirSync(path.join(BASE, runDir));
      const csvName = files.find(f => f.endsWith(".csv"));
      const pyCsv = fs.readFileSync(path.join(BASE, runDir, csvName),
                                    "utf8");
      const att = JSON.parse(fs.readFileSync(
        path.join(BASE, runDir, "run-attestation.json"), "utf8"));
      const jsCsv = eng.scwBuildCSV(got, att.run_id);
      if (jsCsv === pyCsv) console.log("PASS csv " + runDir);
      else { console.error("FAIL csv " + runDir); fail++; }
    }
  } else {
    console.error("FAIL " + inRel + " js!=expected");
    fail++;
  }
}
console.log(fail === 0 ? "PARITY: all engine+sha+csv checks identical" :
  "PARITY FAILED: " + fail);
process.exit(fail === 0 ? 0 : 1);
