/* SCW deterministic rule engine — JavaScript port.
 *
 * Faithful port of src/scw/engine.py (itself a port of the reference in
 * validate.py): pure function evaluate(caseInput, rulePack, engineVersion).
 * No clock, no RNG, no I/O, no network, no LLM. Locked quirks Q1-Q4 apply
 * exactly as documented in engine.py. Byte-parity with the Python engine is
 * proven by tests/parity.js (canonical-string equality on all golden and
 * worked-example vectors). DOM-free: loads in node and in the browser.
 */
"use strict";

var SCW_ENGINE_VERSION = "1.0.0";
var SCW_REFERENCE_VECTOR_ENGINE_VERSION = "0.1.0";

function scwNFC(s) { return s.normalize("NFC"); }

function scwCanonString(obj) {
  return JSON.stringify(scwSortNFC(obj));
}

function scwSortNFC(v) {
  if (typeof v === "string") return scwNFC(v);
  if (Array.isArray(v)) return v.map(scwSortNFC);
  if (v !== null && typeof v === "object") {
    var o = {}, ks = Object.keys(v).sort();
    for (var i = 0; i < ks.length; i++) o[ks[i]] = scwSortNFC(v[ks[i]]);
    return o;
  }
  return v;
}

/* Code-point helpers: Python offsets are Unicode code points, while JS
 * string indices are UTF-16 units. Identical on BMP text; correct anyway. */
function scwCpLen(s) { return Array.from(s).length; }
function scwUnitToCp(s, unitIdx) { return scwCpLen(s.slice(0, unitIdx)); }
function scwCpSlice(s, cpStart, cpEnd) {
  return Array.from(s).slice(cpStart, cpEnd).join("");
}

function scwEscapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function scwEnWordHits(text, surface) {
  var spans = [], re = new RegExp("\\b" + scwEscapeRegExp(surface) + "\\b",
                                  "giu"), m;
  re.lastIndex = 0;
  while ((m = re.exec(text)) !== null) {
    var sCp = scwUnitToCp(text, m.index);
    spans.push([sCp, sCp + scwCpLen(m[0])]);
    if (m.index === re.lastIndex) re.lastIndex++;
  }
  return spans;
}

function scwArHits(ntext, surface) {
  var spans = [], start = 0;
  for (;;) {
    var i = ntext.indexOf(surface, start);
    if (i === -1) return spans;
    var sCp = scwUnitToCp(ntext, i);
    spans.push([sCp, sCp + scwCpLen(surface)]);
    start = i + 1;
  }
}

/* Python str() semantics for field_value comparison (Q-port): booleans
 * render "True"/"False", everything else like String(). */
function scwPyStr(v) {
  if (v === true) return "True";
  if (v === false) return "False";
  if (v === null || v === undefined) return "None";
  return String(v);
}

function scwCitationStatus(pack, citationIds) {
  var byId = {};
  pack.citations.forEach(function (c) { byId[c.citation_id] = c; });
  for (var i = 0; i < citationIds.length; i++) {
    if (byId[citationIds[i]].status === "unverified") return "unverified";
  }
  return "verified";
}

/* The input is normalized ONCE by the caller (NFC) and every
 * match and every slice below runs in that single offset space.
 * Pack surfaces are NFC-normalized before matching for the same
 * reason, so offsets always index ntext. */
function scwRuleEvidenceFreetext(pack, rule, ntext) {
  var evs = [], trig = rule.trigger, i, j, s;
  if (trig.type === "term") {
    for (i = 0; i < trig.term_ids.length; i++) {
      var tid = trig.term_ids[i];
      var entry = null;
      for (j = 0; j < pack.lexicon.length; j++) {
        if (pack.lexicon[j].term_id === tid) entry = pack.lexicon[j];
      }
      var entryEn = scwNFC(entry.en), entryAr = scwNFC(entry.ar);
      var surfaces = [];
      if (surfaces.indexOf(entryEn) === -1) surfaces.push(entryEn);
      if (surfaces.indexOf(entryAr) === -1) surfaces.push(entryAr);
      for (s = 0; s < surfaces.length; s++) {
        var surface = surfaces[s];
        var spans = (surface === entryEn)
          ? scwEnWordHits(ntext, surface)
          : scwArHits(ntext, surface);
        spans.sort(function (a, b) { return a[0] - b[0]; });
        for (j = 0; j < spans.length; j++) {
          evs.push({
            rule_id: rule.rule_id, outcome: rule.outcome,
            severity: rule.severity,
            trigger: { type: "term", term_id: tid, surface_form: surface,
                       match_text: scwCpSlice(ntext, spans[j][0],
                                              spans[j][1]),
                       start_offset: spans[j][0], end_offset: spans[j][1] },
            citation_ids: rule.citation_ids,
            citation_status: scwCitationStatus(pack, rule.citation_ids),
            rationale: rule.rationale
          });
        }
      }
    }
  } else if (trig.type === "regex") {
    var flags = (trig.flags || "").indexOf("i") !== -1 ? "giu" : "gu";
    var re = new RegExp(trig.pattern, flags), m;
    re.lastIndex = 0;
    while ((m = re.exec(ntext)) !== null) {
      var st = scwUnitToCp(ntext, m.index);
      evs.push({
        rule_id: rule.rule_id, outcome: rule.outcome,
        severity: rule.severity,
        trigger: { type: "regex", pattern: trig.pattern,
                   match_text: m[0],
                   start_offset: st, end_offset: st + scwCpLen(m[0]) },
        citation_ids: rule.citation_ids,
        citation_status: scwCitationStatus(pack, rule.citation_ids),
        rationale: rule.rationale
      });
      if (m.index === re.lastIndex) re.lastIndex++;
    }
  }
  return evs;
}

function scwLimitsFor(mode, verdict, anyUnverified, firstItem) {
  var lim = ["single_run_scope"];
  if (verdict === "insufficient_input") lim.push("required_field_missing");
  if (verdict === "out_of_coverage")
    lim.push("no_coverage_outside_lexicon");
  if (verdict === "compliant")
    lim.push("absence_state_not_affirmative_ruling");
  if (mode === "free_text") {
    lim.push("no_stemming_ar");
    if (firstItem) lim.push("unmatched_content_not_assessed");
  }
  if (anyUnverified) lim.push("advisory_only_unverified_citations");
  return lim;
}

function scwDeriveFreetext(pack, inp, packSha, engineVersion) {
  /* Normalize once; match and slice in this one offset space. */
  var ntext = scwNFC(inp.free_text.text), items = [], t, d;
  for (t = 0; t < pack.lexicon.length; t++) {
    var term = pack.lexicon[t];
    var termEn = scwNFC(term.en), termAr = scwNFC(term.ar);
    var surfaces = [];
    if (surfaces.indexOf(termEn) === -1) surfaces.push(termEn);
    if (surfaces.indexOf(termAr) === -1) surfaces.push(termAr);
    var hits = [];
    for (var s = 0; s < surfaces.length; s++) {
      var spans = (surfaces[s] === termEn)
        ? scwEnWordHits(ntext, surfaces[s])
        : scwArHits(ntext, surfaces[s]);
      hits = hits.concat(spans);
    }
    if (!hits.length) continue;
    for (d = 0; d < term.domain_ids.length; d++) {
      var domainId = term.domain_ids[d];
      var evs = [];
      for (var r = 0; r < pack.rules.length; r++) {
        if (pack.rules[r].domain_ids.indexOf(domainId) === -1) continue;
        evs = evs.concat(
          scwRuleEvidenceFreetext(pack, pack.rules[r], ntext));
      }
      evs.sort(function (a, b) {
        return (a.trigger.start_offset || 0) -
               (b.trigger.start_offset || 0);
      });
      var fired = evs.length > 0;
      var verdict = fired ? "doubtful" : "compliant"; /* locked Q2 */
      var anyUn = evs.some(function (e) {
        return e.citation_status === "unverified";
      });
      items.push({
        item_ref: "item-ft-" + term.term_id.replace("term-", ""),
        domain_id: domainId, term_ids: [term.term_id],
        verdict_proposed: verdict, confirmed_by_operator: false,
        verdict_recorded: null, evidence: evs,
        unverified_findings: evs.filter(function (e) {
          return e.citation_status === "unverified";
        }),
        limits_applied: scwLimitsFor("free_text", verdict, anyUn,
                                     items.length === 0)
      });
      break; /* locked Q1: one item per matched term (first domain) */
    }
  }
  return { schema_version: "1.0.0", input_id: inp.input_id,
           rule_pack: { pack_id: pack.pack_id,
                        pack_version: pack.pack_version, sha256: packSha,
                        status: pack.status },
           engine_version: engineVersion, items: items };
}

function scwDeriveGuided(pack, inp, packSha, engineVersion) {
  var domainOf = {}, termsById = {}, i;
  pack.domains.forEach(function (x) { domainOf[x.domain_id] = x; });
  pack.lexicon.forEach(function (x) { termsById[x.term_id] = x; });
  var items = [];
  inp.guided.items.forEach(function (gi) {
    var dom = domainOf[gi.domain_id];
    var required = dom.required_fields || [];
    var missing = required.filter(function (f) {
      var v = (gi.fields || {})[f];
      return v === null || v === undefined ||
        (typeof v === "string" && v === "");
    });
    var inCoverage = gi.term_ids.some(function (t) {
      return termsById[t] && termsById[t].domain_ids &&
        termsById[t].domain_ids.indexOf(gi.domain_id) !== -1;
    });
    var fieldEvs = [], ruleEvs = [];
    pack.rules.forEach(function (rule) {
      if (rule.domain_ids.indexOf(gi.domain_id) === -1) return;
      var trig = rule.trigger, ev = null;
      var has = Object.prototype.hasOwnProperty.call(gi.fields || {},
                                                     trig.field);
      if (trig.type === "field_empty" &&
          (!has || (gi.fields || {})[trig.field] === null ||
           (gi.fields || {})[trig.field] === undefined)) {
        ev = { type: "field_empty", field: trig.field };
      } else if (trig.type === "field_value" &&
                 scwPyStr((gi.fields || {})[trig.field]) ===
                 scwPyStr(trig.equals)) {
        ev = { type: "field_value", field: trig.field,
               value: (gi.fields || {})[trig.field] };
      } else if (trig.type === "term") {
        var inter = trig.term_ids.filter(function (t) {
          return gi.term_ids.indexOf(t) !== -1;
        }).sort();
        if (inter.length) {
          ev = { type: "term_ref", term_id: inter[0],
                 surface_form: termsById[inter[0]].en };
        }
      } else if (trig.type === "regex") {
        return; /* guided mode: regex rules are free-text-only */
      }
      if (ev) {
        var entry = { rule_id: rule.rule_id, outcome: rule.outcome,
                      severity: rule.severity, trigger: ev,
                      citation_ids: rule.citation_ids,
                      citation_status: scwCitationStatus(pack,
                        rule.citation_ids),
                      rationale: rule.rationale };
        if (ev.type === "field_empty") fieldEvs.push(entry);
        else ruleEvs.push(entry);
      }
    });
    var evs = fieldEvs.concat(ruleEvs);
    var anyUn = evs.some(function (e) {
      return e.citation_status === "unverified";
    });
    var verdict;
    if (!inCoverage) verdict = "out_of_coverage";
    else if (missing.length) verdict = "insufficient_input";
    else if (evs.some(function (e) {
      return e.outcome === "non_compliant" &&
        e.citation_status === "verified";
    })) verdict = "non_compliant";
    else if (evs.length) verdict = "doubtful";
    else verdict = "compliant";
    items.push({
      item_ref: gi.item_ref, domain_id: gi.domain_id,
      term_ids: gi.term_ids, verdict_proposed: verdict,
      confirmed_by_operator: true, verdict_recorded: null, evidence: evs,
      unverified_findings: evs.filter(function (e) {
        return e.citation_status === "unverified";
      }),
      limits_applied: scwLimitsFor("guided", verdict, anyUn,
                                   items.length === 0)
    });
  });
  return { schema_version: "1.0.0", input_id: inp.input_id,
           rule_pack: { pack_id: pack.pack_id,
                        pack_version: pack.pack_version, sha256: packSha,
                        status: pack.status },
           engine_version: engineVersion, items: items };
}

function scwCompareVer(a, b) {
  var pa = a.split(".").map(Number), pb = b.split(".").map(Number);
  for (var i = 0; i < 3; i++) {
    if (pa[i] !== pb[i]) return pa[i] - pb[i];
  }
  return 0;
}

function scwEvaluate(caseInput, rulePack, packSha256,
                     engineVersion) {
  engineVersion = engineVersion || SCW_ENGINE_VERSION;
  if (scwCompareVer(engineVersion, rulePack.engine_min_version) < 0 &&
      scwCompareVer(SCW_ENGINE_VERSION, rulePack.engine_min_version) < 0)
    throw new Error("engine below pack engine_min_version");
  if (caseInput.rule_pack_ref.pack_id !== rulePack.pack_id ||
      caseInput.rule_pack_ref.pack_version !== rulePack.pack_version)
    throw new Error("input rule_pack_ref does not name this pack");
  if (caseInput.mode === "free_text")
    return scwDeriveFreetext(rulePack, caseInput, packSha256,
                             engineVersion);
  if (caseInput.mode === "guided")
    return scwDeriveGuided(rulePack, caseInput, packSha256,
                           engineVersion);
  throw new Error("unknown input mode");
}

/* ---- UTF-8 + SHA-256 (sync, dependency-free) ----
 * Single implementation shared by the app and the parity gate.
 * Verified against Python hashlib (see tests/parity.js vectors). */
function scwUtf8(s) { return unescape(encodeURIComponent(s)); }

function scwSha256Hex(ascii) {
  function rotr(v, a) { return (v >>> a) | (v << (32 - a)); }
  var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
           0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  var K = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
           0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
           0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
           0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
           0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
           0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
           0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
           0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
           0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
           0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
           0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
           0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
           0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
           0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
           0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
           0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
  var msgLen = ascii.length;
  var bitHi = Math.floor((msgLen * 8) / Math.pow(2, 32));
  var bitLo = (msgLen * 8) >>> 0;
  ascii += "\x80";
  while (ascii.length % 64 !== 56) ascii += "\x00";
  var words = [], i, c;
  for (i = 0; i < ascii.length; i++) {
    c = ascii.charCodeAt(i);
    if (c > 255) return null;
    var wi = i >> 2;
    words[wi] = (((words[wi] === undefined) ? 0 : words[wi]) |
                 (c << ((3 - (i % 4)) * 8))) | 0;
  }
  words.push(bitHi | 0);
  words.push(bitLo | 0);
  for (var b = 0; b < words.length; b += 16) {
    var w = words.slice(b, b + 16), t;
    for (t = 0; t < 16; t++) w[t] = w[t] | 0;
    for (t = 16; t < 64; t++) {
      var s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^
               (w[t - 15] >>> 3);
      var s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^
               (w[t - 2] >>> 10);
      w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
    }
    var a = H[0], bb = H[1], cc = H[2], dd = H[3],
        ee = H[4], ff = H[5], gg = H[6], hh = H[7];
    for (t = 0; t < 64; t++) {
      var S1 = rotr(ee, 6) ^ rotr(ee, 11) ^ rotr(ee, 25);
      var ch = (ee & ff) ^ ((~ee) & gg);
      var t1 = (hh + S1 + ch + K[t] + w[t]) | 0;
      var S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      var mj = (a & bb) ^ (a & cc) ^ (bb & cc);
      var t2 = (S0 + mj) | 0;
      hh = gg; gg = ff; ff = ee; ee = (dd + t1) | 0;
      dd = cc; cc = bb; bb = a; a = (t1 + t2) | 0;
    }
    H[0] = (H[0] + a) | 0; H[1] = (H[1] + bb) | 0;
    H[2] = (H[2] + cc) | 0; H[3] = (H[3] + dd) | 0;
    H[4] = (H[4] + ee) | 0; H[5] = (H[5] + ff) | 0;
    H[6] = (H[6] + gg) | 0; H[7] = (H[7] + hh) | 0;
  }
  var out = "";
  for (var q = 0; q < 8; q++)
    out += ("00000000" + (H[q] >>> 0).toString(16)).slice(-8);
  return out;
}

/* ---- CSV export (byte-port of Python build_csv; shared app + parity) ---- */
var SCW_CSV_COLUMNS = ["item_ref", "domain_id", "term_ids",
  "verdict_proposed", "confirmed_by_operator", "verdict_recorded",
  "rule_id", "outcome", "severity", "trigger_type", "match_text",
  "start_offset", "end_offset", "citation_ids", "citation_status",
  "rationale_en", "rationale_ar"];

function scwCsvCell(v) {
  v = (v === null || v === undefined) ? "" : String(v);
  return (/[",\n\r]/.test(v)) ? ('"' + v.replace(/"/g, '""') + '"') : v;
}

function scwBuildCSV(result, runId) {
  var L = [];
  function row(cells) {
    L.push(cells.map(scwCsvCell).join(","));
  }
  row(["# SCW single-run CSV export v1"]);
  row(["# run_id", runId]);
  row(["# input_id", result.input_id]);
  row(["# rule_pack_id", result.rule_pack.pack_id]);
  row(["# rule_pack_version", result.rule_pack.pack_version]);
  row(["# rule_pack_sha256", result.rule_pack.sha256]);
  row(["# results_sha256",
       scwSha256Hex(scwUtf8(scwCanonString(result)))]);
  /* Standing export label — byte parity with Python build_csv. */
  row(["# input_status", "unconfirmed input"]);
  row(SCW_CSV_COLUMNS);
  result.items.forEach(function (item) {
    var base = [item.item_ref, item.domain_id,
                (item.term_ids || []).join(";"),
                item.verdict_proposed,
                item.confirmed_by_operator ? "true" : "false",
                (item.verdict_recorded === null ||
                 item.verdict_recorded === undefined) ?
                "" : item.verdict_recorded];
    if (!item.evidence.length) {
      row(base.concat(["", "", "", "", "", "", "", "", "", "", ""]));
      return;
    }
    item.evidence.forEach(function (ev) {
      var t = ev.trigger;
      row(base.concat([ev.rule_id, ev.outcome, ev.severity, t.type,
                       t.match_text || "",
                       (t.start_offset === null ||
                        t.start_offset === undefined) ?
                       "" : t.start_offset,
                       (t.end_offset === null ||
                        t.end_offset === undefined) ?
                       "" : t.end_offset,
                       ev.citation_ids.join(";"), ev.citation_status,
                       ev.rationale.en, ev.rationale.ar || ""]));
    });
  });
  return L.join("\n") + "\n";
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    SCW_ENGINE_VERSION: SCW_ENGINE_VERSION,
    SCW_REFERENCE_VECTOR_ENGINE_VERSION:
      SCW_REFERENCE_VECTOR_ENGINE_VERSION,
    scwCanonString: scwCanonString,
    scwEvaluate: scwEvaluate,
    scwUtf8: scwUtf8,
    scwSha256Hex: scwSha256Hex,
    scwBuildCSV: scwBuildCSV
  };
}
