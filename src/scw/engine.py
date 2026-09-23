"""SCW deterministic rule engine.

Pure function: evaluate(case_input, rule_pack) -> case_result.
No clock, no RNG, no I/O, no network, no LLM. Locked semantics R1-R8 from
the architecture contract; the contract's reference implementation settles every
ambiguity and this module ports it exactly, including two locked quirks:

Q1. Free-text items take the term's FIRST domain only (the reference loops the
    term's domain_ids and breaks after the first). One item per matched term.
Q2. Free-text verdicts are doubtful-if-fired else compliant; the reference never
    emits non_compliant on the free-text path even for verified blocking rules.
Q3. Guided field_empty fires only when the key is absent or null; an empty
    string counts as missing for insufficient_input but does NOT fire the
    field_empty trigger. (Reference lines: `not in` / `is None` vs `== ""`.)
Q4. Guided term triggers intersect single-term rule sets, so the reference's
    set.pop() is deterministic in practice; this port takes the sorted-first
    term id so multi-term intersections stay deterministic by construction.

ENGINE_VERSION 1.0.0 satisfies the starter pack's engine_min_version 1.0.0.
Golden-vector reproduction (A2) is proven by stamping the reference-vector
identity 0.1.0 through the engine_version parameter; live runs always stamp
ENGINE_VERSION (architecture decision D10).
"""
import hashlib
import re
import unicodedata

ENGINE_VERSION = "1.0.0"
REFERENCE_VECTOR_ENGINE_VERSION = "0.1.0"

VERDICTS = ("compliant", "non_compliant", "doubtful",
            "out_of_coverage", "insufficient_input")


def _ver_tuple(v):
    return tuple(int(p) for p in v.split("."))


def assert_engine_compatible(pack):
    """Refuse a pack whose engine_min_version exceeds this engine (arch D2/D4)."""
    minimum = pack.get("engine_min_version", "0.0.0")
    if _ver_tuple(ENGINE_VERSION) < _ver_tuple(minimum):
        raise ValueError("engine %s below pack engine_min_version %s"
                         % (ENGINE_VERSION, minimum))


def check_pack_policy(pack):
    """Semantic policy S1-S7 (architecture contract V2 + citation quote contract S7). Returns the canonical pack sha256.

    Raises ValueError naming the violated gate. Mirrors validate.py V2+S6.
    """
    cit_by_id = {c["citation_id"]: c for c in pack["citations"]}
    term_by_id = {t["term_id"]: t for t in pack["lexicon"]}
    dom_ids = {d["domain_id"] for d in pack["domains"]}

    for r in pack["rules"]:
        for c in r["citation_ids"]:
            if c not in cit_by_id:
                raise ValueError("S1: rule %s cites unknown %s"
                                 % (r["rule_id"], c))
    bad = [r["rule_id"] for r in pack["rules"]
           if r["outcome"] == "non_compliant"
           and any(cit_by_id[c]["status"] == "unverified"
                   for c in r["citation_ids"])]
    if bad:
        raise ValueError("S2: blocking-without-verified-citation: %s" % bad)
    for r in pack["rules"]:
        if not set(r["domain_ids"]) <= dom_ids:
            raise ValueError("S3: rule %s unknown domain" % r["rule_id"])
        if r["trigger"]["type"] == "term":
            for tid in r["trigger"]["term_ids"]:
                if tid not in term_by_id:
                    raise ValueError("S3: rule %s unknown term %s"
                                     % (r["rule_id"], tid))
    for t in pack["lexicon"]:
        if not set(t["domain_ids"]) <= dom_ids:
            raise ValueError("S3: term %s unknown domain" % t["term_id"])
    reg = {u["citation_id"] for u in pack["unverified_sources"]}
    actual = {c["citation_id"] for c in pack["citations"]
              if c["status"] == "unverified"}
    if reg != actual:
        raise ValueError("S4: unverified_sources registry != citations: %s"
                         % sorted(reg ^ actual))
    for r in pack["rules"]:
        if r["severity"] == "advisory" and r["outcome"] != "doubtful":
            raise ValueError("S5: advisory rule %s outcome != doubtful"
                             % r["rule_id"])
    # S7 (citation quote contract): quote-integrity on the RAW pack so the
    # error names the citation. I-Q1 NFC, I-Q2 quote_sha256 recompute;
    # verified rows must carry the full quote contract (I-Q3 whole-doc
    # sha256 presence/shape only offline; live re-fetch is out of scope).
    # I-Q4: unverified rows may omit both, but never carry half a pair.
    for c in pack["citations"]:
        q = c.get("quote")
        qh = c.get("quote_sha256")
        if q is not None or qh is not None:
            if q is None or qh is None or unicodedata.normalize("NFC", q) != q \
                    or hashlib.sha256(q.encode("utf-8")).hexdigest() != qh:
                raise ValueError("S7: quote-integrity violation: %s" % c["citation_id"])
        if c["status"] == "verified":
            if not c.get("sha256") or q is None or qh is None:
                raise ValueError("S7: verified-citation-missing-quote-contract: %s"
                                 % c["citation_id"])
    from .canonical import sha, canon
    pack_sha = sha(canon(pack))
    if len(pack_sha) != 64:
        raise ValueError("S6: pack sha256 malformed")
    return pack_sha


def assert_input_bound(inp, pack):
    """The input's rule_pack_ref must name this pack id+version (arch D3)."""
    ref = inp.get("rule_pack_ref", {})
    if ref.get("pack_id") != pack["pack_id"]:
        raise ValueError("input pack_id %r != pack %r"
                         % (ref.get("pack_id"), pack["pack_id"]))
    if ref.get("pack_version") != pack["pack_version"]:
        raise ValueError("input pack_version %r != pack %r"
                         % (ref.get("pack_version"), pack["pack_version"]))
    if "sha256" in ref and ref["sha256"] is not None:
        from .canonical import sha
        if ref["sha256"] != sha(pack):
            raise ValueError("input pack sha256 != loaded pack sha256")


def _en_word_hits(text, surface):
    return [m.span() for m in
            re.finditer(r"\b" + re.escape(surface) + r"\b", text,
                        re.IGNORECASE)]


def _ar_hits(ntext, surface):
    spans, start = [], 0
    while True:
        i = ntext.find(surface, start)
        if i == -1:
            return spans
        spans.append((i, i + len(surface)))
        start = i + 1


def _citation_status(pack, citation_ids):
    by_id = {c["citation_id"]: c for c in pack["citations"]}
    return ("unverified"
            if any(by_id[c]["status"] == "unverified" for c in citation_ids)
            else "verified")


def _rule_evidence_freetext(pack, rule, ntext):
    # The input is normalized ONCE by the caller (NFC) and every
    # match and every slice below runs in that single offset space.
    # Pack surfaces are NFC-normalized before matching for the same
    # reason, so offsets always index ntext.
    evs = []
    trig = rule["trigger"]
    if trig["type"] == "term":
        for tid in trig["term_ids"]:
            entry = next(t for t in pack["lexicon"] if t["term_id"] == tid)
            for surface in {unicodedata.normalize("NFC", entry["en"]),
                            unicodedata.normalize("NFC", entry["ar"])}:
                if surface == unicodedata.normalize("NFC", entry["en"]):
                    spans = _en_word_hits(ntext, surface)
                else:
                    spans = _ar_hits(ntext, surface)
                for s, e in sorted(spans):
                    evs.append({
                        "rule_id": rule["rule_id"],
                        "outcome": rule["outcome"],
                        "severity": rule["severity"],
                        "trigger": {"type": "term", "term_id": tid,
                                    "surface_form": surface,
                                    "match_text": ntext[s:e],
                                    "start_offset": s, "end_offset": e},
                        "citation_ids": rule["citation_ids"],
                        "citation_status": _citation_status(
                            pack, rule["citation_ids"]),
                        "rationale": rule["rationale"]})
    elif trig["type"] == "regex":
        flags = re.IGNORECASE if "i" in trig.get("flags", "") else 0
        for m in re.finditer(trig["pattern"], ntext, flags):
            evs.append({
                "rule_id": rule["rule_id"], "outcome": rule["outcome"],
                "severity": rule["severity"],
                "trigger": {"type": "regex", "pattern": trig["pattern"],
                            "match_text": m.group(0),
                            "start_offset": m.start(),
                            "end_offset": m.end()},
                "citation_ids": rule["citation_ids"],
                "citation_status": _citation_status(pack,
                                                    rule["citation_ids"]),
                "rationale": rule["rationale"]})
    return evs


def _limits_for(mode, verdict, any_unverified, first_item):
    lim = ["single_run_scope"]
    if verdict == "insufficient_input":
        lim.append("required_field_missing")
    if verdict == "out_of_coverage":
        lim.append("no_coverage_outside_lexicon")
    if verdict == "compliant":
        lim.append("absence_state_not_affirmative_ruling")
    if mode == "free_text":
        lim.append("no_stemming_ar")
        if first_item:
            lim.append("unmatched_content_not_assessed")
    if any_unverified:
        lim.append("advisory_only_unverified_citations")
    return lim


def _derive_freetext(pack, inp, pack_sha, engine_version):
    # Normalize once; match and slice in this one offset space.
    ntext = unicodedata.normalize("NFC", inp["free_text"]["text"])
    items = []
    for term in pack["lexicon"]:
        surfaces = {(s, s == unicodedata.normalize("NFC", term["en"]))
                    for s in {unicodedata.normalize("NFC", term["en"]),
                              unicodedata.normalize("NFC", term["ar"])}}
        hits = []
        for surface, is_en in surfaces:
            spans = (_en_word_hits(ntext, surface) if is_en
                     else _ar_hits(ntext, surface))
            hits += spans
        if not hits:
            continue
        for domain_id in term["domain_ids"]:
            evs = []
            for rule in pack["rules"]:
                if domain_id not in rule["domain_ids"]:
                    continue
                evs += _rule_evidence_freetext(pack, rule, ntext)
            evs.sort(key=lambda e: e["trigger"].get("start_offset", 0))
            fired = len(evs) > 0
            verdict = "doubtful" if fired else "compliant"  # locked Q2
            any_unverified = any(e["citation_status"] == "unverified"
                                 for e in evs)
            items.append({
                "item_ref": "item-ft-" + term["term_id"].replace("term-", ""),
                "domain_id": domain_id, "term_ids": [term["term_id"]],
                "verdict_proposed": verdict,
                "confirmed_by_operator": False, "verdict_recorded": None,
                "evidence": evs,
                "unverified_findings": [
                    e for e in evs if e["citation_status"] == "unverified"],
                "limits_applied": _limits_for(
                    "free_text", verdict, any_unverified,
                    len(items) == 0)})
            break  # locked Q1: one item per matched term (first domain)
    return {"schema_version": "1.0.0", "input_id": inp["input_id"],
            "rule_pack": {"pack_id": pack["pack_id"],
                          "pack_version": pack["pack_version"],
                          "sha256": pack_sha, "status": pack["status"]},
            "engine_version": engine_version, "items": items}


def _derive_guided(pack, inp, pack_sha, engine_version):
    domain_of = {d["domain_id"]: d for d in pack["domains"]}
    terms_by_id = {t["term_id"]: t for t in pack["lexicon"]}
    items = []
    for gi in inp["guided"]["items"]:
        dom = domain_of[gi["domain_id"]]
        missing = [f for f in dom.get("required_fields", [])
                   if gi["fields"].get(f) is None
                   or (isinstance(gi["fields"].get(f), str)
                       and gi["fields"].get(f) == "")]
        in_coverage = any(terms_by_id[t]["domain_ids"]
                          and gi["domain_id"] in terms_by_id[t]["domain_ids"]
                          for t in gi["term_ids"] if t in terms_by_id)
        field_evs, rule_evs = [], []
        for rule in pack["rules"]:
            if gi["domain_id"] not in rule["domain_ids"]:
                continue
            trig = rule["trigger"]
            ev = None
            if trig["type"] == "field_empty" and (
                    trig["field"] not in gi["fields"]
                    or gi["fields"].get(trig["field"]) is None):
                ev = {"type": "field_empty", "field": trig["field"]}
            elif (trig["type"] == "field_value"
                  and str(gi["fields"].get(trig["field"]))
                  == str(trig["equals"])):
                ev = {"type": "field_value", "field": trig["field"],
                      "value": gi["fields"].get(trig["field"])}
            elif (trig["type"] == "term"
                  and set(trig["term_ids"]) & set(gi["term_ids"])):
                tid = sorted(set(trig["term_ids"])
                             & set(gi["term_ids"]))[0]  # locked Q4
                ev = {"type": "term_ref", "term_id": tid,
                      "surface_form": terms_by_id[tid]["en"]}
            elif trig["type"] == "regex":
                continue  # guided mode: regex rules are free-text-only
            if ev:
                entry = {"rule_id": rule["rule_id"],
                         "outcome": rule["outcome"],
                         "severity": rule["severity"],
                         "trigger": ev,
                         "citation_ids": rule["citation_ids"],
                         "citation_status": _citation_status(
                             pack, rule["citation_ids"]),
                         "rationale": rule["rationale"]}
                (field_evs if ev["type"] == "field_empty"
                 else rule_evs).append(entry)
        evs = field_evs + rule_evs
        any_unverified = any(e["citation_status"] == "unverified"
                             for e in evs)
        if not in_coverage:
            verdict = "out_of_coverage"
        elif missing:
            verdict = "insufficient_input"
        elif any(e["outcome"] == "non_compliant"
                 and e["citation_status"] == "verified" for e in evs):
            verdict = "non_compliant"
        elif evs:
            verdict = "doubtful"
        else:
            verdict = "compliant"
        items.append({
            "item_ref": gi["item_ref"], "domain_id": gi["domain_id"],
            "term_ids": gi["term_ids"],
            "verdict_proposed": verdict, "confirmed_by_operator": True,
            "verdict_recorded": None, "evidence": evs,
            "unverified_findings": [
                e for e in evs if e["citation_status"] == "unverified"],
            "limits_applied": _limits_for("guided", verdict, any_unverified,
                                          len(items) == 0)})
    return {"schema_version": "1.0.0", "input_id": inp["input_id"],
            "rule_pack": {"pack_id": pack["pack_id"],
                          "pack_version": pack["pack_version"],
                          "sha256": pack_sha, "status": pack["status"]},
            "engine_version": engine_version, "items": items}


def evaluate(case_input, rule_pack, engine_version=ENGINE_VERSION):
    """Pure deterministic evaluation (R1-R8). Raises ValueError on refusal."""
    assert_engine_compatible(rule_pack)
    pack_sha = check_pack_policy(rule_pack)
    assert_input_bound(case_input, rule_pack)
    mode = case_input.get("mode")
    if mode == "free_text":
        return _derive_freetext(rule_pack, case_input, pack_sha,
                                engine_version)
    if mode == "guided":
        return _derive_guided(rule_pack, case_input, pack_sha,
                              engine_version)
    raise ValueError("unknown input mode %r" % (mode,))
