"""SCW stdlib-only structural validation.

The four LOCKED JSON Schemas (schemas/*.json, draft 2020-12) are the
normative interfaces and ship byte-identical from the architecture contract. This module
is a stdlib-only structural gate covering the constraints the runtime depends
on (required keys, closed keys, enums, consts, key patterns, verdict tokens,
blank sign-off, run_id formula, hash formats) so `run_tests.sh` stays green
on a bare macOS Python with no third-party packages and no network.
It is NOT a general JSON-Schema validator; full draft 2020-12 conformance is
proven by the architecture contract's validation harness.
"""
import re

from .engine import VERDICTS

_ERRORS = []

RE_PACK_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
RE_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
RE_DOMAIN = re.compile(r"^d_[a-z][a-z0-9_]{2,31}$")
RE_TERM = re.compile(r"^term-[a-z0-9-]{1,63}$")
RE_CIT = re.compile(r"^cit-[a-z0-9-]{1,63}$")
RE_RULE = re.compile(r"^rule-[a-z0-9-]{1,63}$")
RE_FIELD = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
RE_ITEM = re.compile(r"^item-[a-z0-9-]{1,63}$")
RE_HEX64 = re.compile(r"^[a-f0-9]{64}$")
RE_RUNID = re.compile(r"^run-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
RE_INPUTID = re.compile(r"^ci-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
                        r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
RE_INPUTID_LOOSE = re.compile(r"^ci-[0-9a-f-]{36}$")


def _err(path, msg):
    _ERRORS.append("%s: %s" % (path, msg))


def _req(obj, path, keys, closed):
    if not isinstance(obj, dict):
        _err(path, "not an object")
        return False
    ok = True
    for k in keys:
        if k not in obj:
            _err(path, "missing required %r" % k)
            ok = False
    if closed:
        for k in obj:
            if k not in keys:
                _err(path, "closed object, extra key %r" % k)
                ok = False
    return ok


def _loc(obj, path, ar_nullable=True):
    keys = ["en"] if obj.get("ar", "missing") == "missing" else ["en", "ar"]
    if not _req(obj, path, keys, True):
        return False
    if not isinstance(obj["en"], str) or not obj["en"]:
        _err(path, "en must be a non-empty string")
        return False
    if "ar" in obj and obj["ar"] is not None \
            and not isinstance(obj["ar"], str):
        _err(path, "ar must be string|null")
        return False
    return True


def check_pack(pack):
    _ERRORS.clear()
    base = ["pack_id", "schema_version", "pack_version", "created_utc",
            "status", "engine_min_version", "domains", "lexicon",
            "citations", "unverified_sources", "rules"]
    if not _req(pack, "pack", base, True):
        return list(_ERRORS)
    if not RE_PACK_ID.match(pack["pack_id"]):
        _err("pack_id", "pattern")
    if pack["schema_version"] != "1.1.0":
        _err("schema_version", "must be const 1.1.0")
    if not RE_SEMVER.match(pack["pack_version"]):
        _err("pack_version", "semver")
    if pack["status"] not in ("draft", "stable", "retired"):
        _err("status", "enum")
    for i, d in enumerate(pack["domains"]):
        p = "domains[%d]" % i
        if not _req(d, p, ["domain_id", "label"], False):
            continue
        if not RE_DOMAIN.match(d["domain_id"]):
            _err(p, "domain_id pattern")
        _loc(d["label"], p + ".label")
        for f in d.get("required_fields", []):
            if not RE_FIELD.match(f):
                _err(p, "required_field pattern %r" % f)
    for i, t in enumerate(pack["lexicon"]):
        p = "lexicon[%d]" % i
        if not _req(t, p, ["term_id", "en", "ar", "domain_ids"], False):
            continue
        if not RE_TERM.match(t["term_id"]):
            _err(p, "term_id pattern")
    for i, c in enumerate(pack["citations"]):
        p = "citations[%d]" % i
        if not _req(c, p, ["citation_id", "status", "title", "url",
                           "fetch_date"], False):
            continue
        if not RE_CIT.match(c["citation_id"]):
            _err(p, "citation_id pattern")
        if c["status"] not in ("verified", "unverified"):
            _err(p, "status enum")
            continue
        # Citation-integrity contract (structural mirror of S7):
        # verified rows must carry sha256 + quote + quote_sha256;
        # quote/quote_sha256 pair fail-closed on any status (shape only;
        # hash math lives in engine.check_pack_policy S7).
        if c["status"] == "verified":
            for k in ("sha256", "quote", "quote_sha256"):
                if not c.get(k):
                    _err(p, "verified citation missing %r" % k)
            for k in ("sha256", "quote_sha256"):
                if c.get(k) and not RE_HEX64.match(c[k]):
                    _err(p, "%s hex64" % k)
            if c.get("quote") is not None and not isinstance(
                    c["quote"], str):
                _err(p, "quote must be a string")
            elif isinstance(c.get("quote"), str) and not c["quote"]:
                _err(p, "quote must be non-empty")
        else:
            q, qh = c.get("quote"), c.get("quote_sha256")
            if (q is None) != (qh is None):
                _err(p, "quote/quote_sha256 must pair or both be absent")
            elif q is not None:
                if not isinstance(q, str) or not q:
                    _err(p, "quote must be a non-empty string")
                if not RE_HEX64.match(qh or ""):
                    _err(p, "quote_sha256 hex64")
    for i, u in enumerate(pack["unverified_sources"]):
        if not _req(u, "unverified_sources[%d]" % i,
                    ["citation_id", "reason"], True):
            continue
    for i, r in enumerate(pack["rules"]):
        p = "rules[%d]" % i
        if not _req(r, p, ["rule_id", "domain_ids", "outcome", "severity",
                           "trigger", "rationale", "citation_ids",
                           "status"], True):
            continue
        if not RE_RULE.match(r["rule_id"]):
            _err(p, "rule_id pattern")
        if r["outcome"] not in ("non_compliant", "doubtful"):
            _err(p, "outcome enum")
        if r["severity"] not in ("blocking", "advisory"):
            _err(p, "severity enum")
        if r["status"] not in ("active", "retired"):
            _err(p, "status enum")
        _loc(r["rationale"], p + ".rationale")
        trig = r["trigger"]
        ttype = trig.get("type")
        if ttype == "term":
            if not _req(trig, p + ".trigger", ["type", "term_ids"], True):
                pass
        elif ttype == "regex":
            if not _req(trig, p + ".trigger", ["type", "pattern"], False):
                pass
        elif ttype == "field_empty":
            _req(trig, p + ".trigger", ["type", "field"], True)
        elif ttype == "field_value":
            _req(trig, p + ".trigger", ["type", "field", "equals"], True)
        else:
            _err(p + ".trigger", "unknown trigger type %r" % (ttype,))
    return list(_ERRORS)


def check_input(inp, strict_id=True):
    _ERRORS.clear()
    if not _req(inp, "input", ["input_id", "mode", "created_utc",
                               "rule_pack_ref"], False):
        return list(_ERRORS)
    pat = RE_INPUTID if strict_id else RE_INPUTID_LOOSE
    if not pat.match(inp["input_id"]):
        _err("input_id", "pattern")
    if inp["mode"] not in ("guided", "free_text"):
        _err("mode", "enum")
    ref = inp["rule_pack_ref"]
    if not _req(ref, "rule_pack_ref", ["pack_id", "pack_version"], False):
        pass
    if inp["mode"] == "guided":
        g = inp.get("guided")
        if not isinstance(g, dict) or not isinstance(g.get("items"), list) \
                or not g["items"]:
            _err("guided", "needs non-empty items")
        else:
            for i, gi in enumerate(g["items"]):
                p = "guided.items[%d]" % i
                if not _req(gi, p, ["item_ref", "domain_id", "term_ids",
                                    "fields"], False):
                    continue
                if not RE_ITEM.match(gi["item_ref"]):
                    _err(p, "item_ref pattern")
                if not RE_DOMAIN.match(gi["domain_id"]):
                    _err(p, "domain_id pattern")
    if inp["mode"] == "free_text":
        f = inp.get("free_text")
        if not isinstance(f, dict) or not isinstance(f.get("text"), str) \
                or not f["text"]:
            _err("free_text", "needs non-empty text")
    return list(_ERRORS)


def _check_trigger_evidence(trig, path):
    t = trig.get("type")
    if t == "term_ref":
        _req(trig, path, ["type", "term_id", "surface_form"], True)
    elif t == "term":
        _req(trig, path,
             ["type", "term_id", "surface_form", "match_text",
              "start_offset", "end_offset"], True)
    elif t == "regex":
        _req(trig, path,
             ["type", "pattern", "match_text", "start_offset",
              "end_offset"], True)
    elif t == "field_empty":
        _req(trig, path, ["type", "field"], True)
    elif t == "field_value":
        _req(trig, path, ["type", "field", "value"], True)
    else:
        _err(path, "unknown evidence trigger %r" % (t,))


def check_result(res):
    _ERRORS.clear()
    if not _req(res, "result",
                    ["schema_version", "input_id", "rule_pack",
                     "engine_version", "items"], True):
        return list(_ERRORS)
    if res["schema_version"] != "1.0.0":
        _err("schema_version", "const 1.0.0")
    if not RE_INPUTID_LOOSE.match(res["input_id"]):
        _err("input_id", "pattern")
    rp = res["rule_pack"]
    if not _req(rp, "rule_pack",
                    ["pack_id", "pack_version", "sha256", "status"], True):
        pass
    elif not RE_HEX64.match(rp["sha256"]):
        _err("rule_pack.sha256", "hex64")
    if not RE_SEMVER.match(res["engine_version"]):
        _err("engine_version", "semver")
    if not isinstance(res["items"], list) or not res["items"]:
        _err("items", "non-empty array")
        return list(_ERRORS)
    for i, item in enumerate(res["items"]):
        p = "items[%d]" % i
        if not _req(item, p,
                        ["item_ref", "domain_id", "verdict_proposed",
                         "evidence", "confirmed_by_operator",
                         "verdict_recorded"], False):
            continue
        if item["verdict_proposed"] not in VERDICTS:
            _err(p, "verdict outside locked five-token set: %r"
                 % (item["verdict_proposed"],))
        vr = item["verdict_recorded"]
        if vr is not None and vr not in VERDICTS:
            _err(p, "verdict_recorded outside locked set")
        for j, ev in enumerate(item["evidence"]):
            ep = "%s.evidence[%d]" % (p, j)
            if not _req(ev, ep,
                            ["rule_id", "outcome", "severity", "trigger",
                             "citation_ids", "citation_status"], False):
                continue
            if ev["outcome"] not in ("non_compliant", "doubtful"):
                _err(ep, "outcome enum")
            if ev["citation_status"] not in ("verified", "unverified"):
                _err(ep, "citation_status enum")
            _check_trigger_evidence(ev["trigger"], ep + ".trigger")
    return list(_ERRORS)


def check_attestation(att, input_sha=None, results_sha=None, pack_sha=None,
                      run_started=None):
    _ERRORS.clear()
    keys = ["attestation_version", "run_id", "clock_source",
            "run_started_utc", "run_finished_utc", "offline_assertion",
            "input_id", "input_sha256", "rule_pack", "engine_version",
            "results_sha256", "verdict_counts", "exports",
            "reviewer_signoff", "disclaimer"]
    if not _req(att, "attestation", keys, True):
        return list(_ERRORS)
    if att["attestation_version"] != "1.0.0":
        _err("attestation_version", "const 1.0.0")
    if not RE_RUNID.match(att["run_id"]):
        _err("run_id", "pattern")
    if run_started is not None:
        expect = "run-%s-%s" % (run_started.replace("-", "")
                                 .replace(":", ""), att["input_sha256"][:8])
        if att["run_id"] != expect:
            _err("run_id", "derivation != %s" % expect)
    if att["clock_source"] != "local":
        _err("clock_source", "const local")
    off = att["offline_assertion"]
    if off != {"network_calls_made": False,
               "engine_is_deterministic": True, "llm_invoked": False}:
        _err("offline_assertion", "const triple")
    if not RE_HEX64.match(att["input_sha256"]):
        _err("input_sha256", "hex64")
    if not RE_HEX64.match(att["results_sha256"]):
        _err("results_sha256", "hex64")
    if input_sha is not None and att["input_sha256"] != input_sha:
        _err("input_sha256", "!= canonical input hash")
    if results_sha is not None and att["results_sha256"] != results_sha:
        _err("results_sha256", "!= canonical result hash")
    if pack_sha is not None and att["rule_pack"]["sha256"] != pack_sha:
        _err("rule_pack.sha256", "!= pack hash")
    vc = att["verdict_counts"]
    if sorted(vc.keys()) != sorted(VERDICTS):
        _err("verdict_counts", "must carry all five tokens")
    ex = att["exports"]
    if not isinstance(ex, list) or len(ex) != 1:
        _err("exports", "exactly one (csv) entry")
    elif ex[0].get("kind") != "csv" or not RE_HEX64.match(
            ex[0].get("sha256", "")):
        _err("exports[0]", "kind csv + hex64 sha256")
    if att["reviewer_signoff"] != {"reviewer_name": "",
                                   "reviewer_role": "",
                                   "review_date": "", "statement": None,
                                   "completed": False}:
        _err("reviewer_signoff", "must be schema-const blank")
    disc = att["disclaimer"]
    if not isinstance(disc.get("en"), str) or len(disc["en"]) < 20:
        _err("disclaimer", "en minLength 20")
    return list(_ERRORS)
