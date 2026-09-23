"""SCW export builders: CSV (locked columns) + print-ready HTML.

CSV is a byte-exact port of the architecture contract's reference build_csv: fixed `#` header
block, locked column set, LF endings, UTF-8 no BOM, RFC 4180 quoting.
HTML is a single file with zero external resources: result items with
evidence, bilingual rationales, the attestation embedded verbatim, the blank
sign-off block, the disclaimer, and the eight coverage limits (UX contract
wording, substance-verbatim from architecture decision D10).
"""
import csv
import html
import io

from .canonical import sha, canon

CSV_COLUMNS = ["item_ref", "domain_id", "term_ids", "verdict_proposed",
               "confirmed_by_operator", "verdict_recorded", "rule_id",
               "outcome", "severity", "trigger_type", "match_text",
               "start_offset", "end_offset", "citation_ids",
               "citation_status", "rationale_en", "rationale_ar"]

# Owner-gloss mapping (UX contract): schema token -> worksheet word.
GLOSS = {"compliant": "Met", "non_compliant": "Gap", "doubtful": "Unverified",
         "out_of_coverage": "Not applicable",
         "insufficient_input": "Needs evidence"}

# Eight coverage limits, substance-verbatim from the UX content inventory
# (which is substance-verbatim from the architecture contract).
LIMITS = [
    ("limit-1",
     "The pack covers murabaha, ijara, takaful and related structures "
     "across four domains. Anything outside the lexicon is \u201cnot "
     "covered\u201d \u2014 never \u201ccompliant by silence\u201d.",
     "\u062a\u063a\u0637\u064a \u0647\u0630\u0647 \u0627\u0644\u062d\u0632\u0645\u0629 "
     "\u0627\u0644\u0645\u0631\u0627\u0628\u062d\u0629 \u0648\u0627\u0644\u0625\u062c\u0627\u0631\u0629 "
     "\u0648\u0627\u0644\u062a\u0643\u0627\u0641\u0644 \u0648\u0627\u0644\u0628\u0646\u064a\u0629 "
     "\u0630\u0627\u062a \u0627\u0644\u0635\u0644\u0629 \u0639\u0628\u0631 \u0623\u0631\u0628\u0639\u0629 "
     "\u0646\u0637\u0627\u0642\u0627\u062a. \u0648\u0643\u0644 \u0645\u0627 \u0647\u0648 \u062e\u0627\u0631\u062c "
     "\u0627\u0644\u0645\u0639\u062c\u0645 \u064a\u064f\u0639\u0644\u064e\u0651\u0645 "
     "\u00ab\u063a\u064a\u0631 \u0645\u063a\u0637\u0649\u00bb\u060c \u0648\u0644\u0627 "
     "\u064a\u064f\u0639\u0627\u0645\u0644 \u00ab\u0645\u0637\u0627\u0628\u0642\u064b\u0627\u00bb "
     "\u0628\u0642\u0631\u0627\u0631 \u0636\u0645\u0646\u064a."),
    ("limit-2",
     "Free-text matching is exact-surface only \u2014 no stemming and no "
     "Arabic morphology; definite-article and inflected Arabic forms will "
     "not match. The guided form is the completeness instrument.",
     "\u0645\u0637\u0627\u0628\u0642\u0629 \u0627\u0644\u0646\u0635 \u0627\u0644\u062d\u0631 "
     "\u062a\u0639\u062a\u0645\u062f \u0627\u0644\u0645\u0637\u0627\u0628\u0642\u0629 "
     "\u0627\u0644\u062d\u0631\u0641\u064a\u0629 \u0627\u0644\u062f\u0642\u064a\u0642\u0629 "
     "\u0641\u0642\u0637\u060c \u0628\u0644\u0627 \u062c\u0630\u0648\u0631 \u0648\u0644\u0627 "
     "\u0635\u0631\u0641 \u0639\u0631\u0628\u064a\u061b \u0627\u0644\u0634\u0643\u0644 "
     "\u0627\u0644\u0645\u0639\u0631\u064e\u0651\u0641 \u0648\u0627\u0644\u0623\u0634\u0643\u0627\u0644 "
     "\u0627\u0644\u0645\u064f\u0639\u0631\u0628\u064e\u0651\u0629 \u0644\u0627 "
     "\u062a\u062a\u0637\u0627\u0628\u0642. \u0627\u0644\u0646\u0645\u0648\u0630\u062c "
     "\u0627\u0644\u0645\u0648\u062c\u064e\u0651\u0647 \u0647\u0648 \u0623\u062f\u0627\u0629 "
     "\u0627\u0644\u0625\u0643\u0645\u0627\u0644."),
    ("limit-3",
     "Content that matches nothing in free-text mode is NOT assessed; a "
     "single reminder rides on the first proposed item.",
     "\u0627\u0644\u0630\u064a \u0644\u0627 \u064a\u0637\u0627\u0628\u0642 \u0634\u064a\u0626\u064b\u0627 "
     "\u0641\u064a \u0648\u0636\u0639 \u0627\u0644\u0646\u0635 \u0627\u0644\u062d\u0631 \u0644\u0627 "
     "\u064a\u064f\u0642\u064a\u064e\u0651\u0645\u061b \u0648\u064a\u0638\u0647\u0631 \u062a\u0646\u0628\u064a\u0647 "
     "\u0648\u0627\u062d\u062f \u0639\u0644\u0649 \u0623\u0648\u0644 \u0628\u0646\u062f \u0645\u0642\u062a\u0631\u062d."),
    ("limit-4",
     "\u201ccompliant\u201d is an absence state, not an affirmative ruling.",
     "\u00abcompliant\u00bb \u062d\u0627\u0644\u0629 \u063a\u064a\u0627\u0628 "
     "\u0648\u0644\u064a\u0633\u062a \u062d\u0643\u0645\u064b\u0627 \u0625\u064a\u062c\u0627\u0628\u064a\u064b\u0627."),
    ("limit-5",
     "\u201cnon_compliant\u201d is unreachable until the pack ships a "
     "blocking rule backed by fetched, hashed primary sources.",
     "\u00abnon_compliant\u00bb \u063a\u064a\u0631 \u0642\u0627\u0628\u0644 "
     "\u0644\u0644\u0648\u0635\u0648\u0644 \u062d\u062a\u0649 \u062a\u0635\u062f\u0631 "
     "\u0627\u0644\u062d\u0632\u0645\u0629 \u0642\u0627\u0639\u062f\u0629 \u0645\u0627\u0646\u0639\u0629 "
     "\u062a\u0633\u062a\u0646\u062f \u0625\u0644\u0649 \u0645\u0635\u0627\u062f\u0631 \u0623\u0635\u0644\u064a\u0629 "
     "\u0645\u064f\u062c\u0644\u0628\u0629 \u0648\u0644\u0647\u0627 \u0628\u0635\u0645\u0629 sha256 "
     "\u0645\u0633\u062c\u064e\u0651\u0644\u0629."),
    ("limit-6",
     "Runs are single-run, stateless; nothing accumulates across runs.",
     "\u0627\u0644\u062a\u0634\u063a\u064a\u0644\u0627\u062a \u0645\u0641\u0631\u062f\u0629 "
     "\u0648\u063a\u064a\u0631 \u062d\u0627\u0644\u062a\u064a\u0629\u061b \u0644\u0627 "
     "\u064a\u062a\u0631\u0627\u0643\u0645 \u0634\u064a\u0621 \u0628\u064a\u0646 \u0639\u0645\u0644\u064a\u0627\u062a "
     "\u0627\u0644\u062a\u0634\u063a\u064a\u0644."),
    ("limit-7",
     "Timestamps are local wall clock \u2014 provenance metadata only, "
     "never verdict inputs.",
     "\u0627\u0644\u062a\u0648\u0642\u064a\u062a\u0627\u062a \u0645\u0646 \u0633\u0627\u0639\u0629 "
     "\u0627\u0644\u062c\u0647\u0627\u0632 \u0627\u0644\u0645\u062d\u0644\u064a\u0629 \u2014 "
     "\u0628\u064a\u0627\u0646\u0627\u062a \u0625\u062b\u0628\u0627\u062a \u0623\u0635\u0644 \u0641\u0642\u0637\u060c "
     "\u0648\u0644\u064a\u0633\u062a \u0645\u062f\u062e\u0644\u0627\u062a \u0644\u0623\u064a \u062d\u0643\u0645."),
    ("limit-8",
     "The workbook is a drafting aid; verdicts are proposals pending human "
     "review and sign-off; not legal or sharia advice.",
     "\u0627\u0644\u062f\u0641\u062a\u0631 \u0623\u062f\u0627\u0629 \u0645\u0633\u0627\u0639\u062f\u0629 "
     "\u0644\u0644\u0625\u0639\u062f\u0627\u062f\u061b \u0627\u0644\u0623\u062d\u0643\u0627\u0645 "
     "\u0645\u0642\u062a\u0631\u062d\u0627\u062a \u062a\u0646\u062a\u0638\u0631 \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629 "
     "\u0627\u0644\u0628\u0634\u0631\u064a\u0629 \u0648\u0627\u0644\u0627\u0639\u062a\u0645\u0627\u062f\u061b "
     "\u0644\u064a\u0633\u062a \u0645\u0634\u0648\u0631\u0629 \u0642\u0627\u0646\u0648\u0646\u064a\u0629 "
     "\u0623\u0648 \u0634\u0631\u0639\u064a\u0629."),
]


def build_csv(result, run_id):
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["# SCW single-run CSV export v1"])
    w.writerow(["# run_id", run_id])
    w.writerow(["# input_id", result["input_id"]])
    w.writerow(["# rule_pack_id", result["rule_pack"]["pack_id"]])
    w.writerow(["# rule_pack_version", result["rule_pack"]["pack_version"]])
    w.writerow(["# rule_pack_sha256", result["rule_pack"]["sha256"]])
    w.writerow(["# results_sha256", sha(canon(result))])
    # Standing export label — every export carries the unconfirmed
    # input status on every run (UX contract, label-only row).
    w.writerow(["# input_status", "unconfirmed input"])
    w.writerow(CSV_COLUMNS)
    for item in result["items"]:
        base = [item["item_ref"], item["domain_id"],
                ";".join(item.get("term_ids", [])),
                item["verdict_proposed"],
                str(item["confirmed_by_operator"]).lower(),
                "" if item["verdict_recorded"] is None
                else item["verdict_recorded"]]
        if not item["evidence"]:
            w.writerow(base + ["", "", "", "", "", "", "", "", "", "", ""])
        for ev in item["evidence"]:
            trig = ev["trigger"]
            w.writerow(base + [
                ev["rule_id"], ev["outcome"], ev["severity"],
                trig["type"], trig.get("match_text", ""),
                str(trig.get("start_offset", "")),
                str(trig.get("end_offset", "")),
                ";".join(ev["citation_ids"]), ev["citation_status"],
                ev["rationale"]["en"],
                ev["rationale"].get("ar") or ""])
    return out.getvalue().encode("utf-8")


def _esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def build_html(result, attestation, pack):
    """Single-file print-ready worksheet. Zero external resources."""
    cit_title = {c["citation_id"]: c for c in pack["citations"]}
    parts = []
    a = parts.append
    a("<!DOCTYPE html>")
    a("<html lang=\"en\" dir=\"ltr\">")
    a("<head><meta charset=\"utf-8\">")
    a("<title>Sharia-Compliance Workbook \u2014 single-run worksheet</title>")
    a("<style>")
    a("body{font-family:Georgia,'Times New Roman',serif;color:#111;"
      "background:#fff;max-width:210mm;margin:0 auto;padding:12mm;}")
    a(".ar{direction:rtl;text-align:right;}")
    a("table{width:100%;border-collapse:collapse;margin:1em 0;}")
    a("th,td{border:1px solid #444;padding:.4em;vertical-align:top;"
      "text-align:left;}")
    a("thead{display:table-header-group;}")
    a("tr,section{break-inside:avoid;}")
    a(".badge{display:inline-block;border:1px solid #111;border-radius:4px;"
      "padding:.1em .5em;margin:.1em;font-size:.9em;}")
    a(".alert{border:2px solid #111;padding:.6em;margin:.6em 0;}")
    a(".signoff{border:2px solid #111;padding:1em;margin-top:2em;}")
    a(".gap{border:1px dashed #666;padding:.3em;background:#f6f6f6;}")
    a("@page{size:A4;margin:15mm;}")
    a("@media print{.noprint{display:none;}}")
    a("</style></head><body>")
    a("<h1>Sharia-Compliance Workbook \u2014 mapping worksheet</h1>")
    # Standing export label immediately after the <h1>, before the
    # drafting-aid paragraph and every verdict row (UX contract:
    # offset of the EN label < offset of first <h2).
    a("<p class=\"alert\" data-statuslabel><strong>Input status: unconfirmed "
      "input</strong> \u2014 this document has not been reviewed and carries "
      "no reviewer sign-off.<br><span class=\"ar\" dir=\"rtl\" lang=\"ar\">"
      "\u062d\u0627\u0644\u0629 \u0627\u0644\u0645\u062f\u062e\u0644\u0627\u062a: "
      "\u0645\u062f\u062e\u0644\u0627\u062a \u063a\u064a\u0631 \u0645\u0624\u0643\u062f\u0629 "
      "\u2014 \u0644\u0645 \u062a\u064f\u0631\u0627\u062c\u0639 \u0647\u0630\u0647 "
      "\u0627\u0644\u0648\u062b\u064a\u0642\u0629 \u0648\u0644\u0627 \u062a\u062d\u0645\u0644 "
      "\u0627\u0639\u062a\u0645\u0627\u062f \u0645\u0631\u0627\u062c\u0639.</span></p>")
    a("<p><strong>Drafting aid only \u2014 not legal advice, not a fatwa, "
      "not regulatory approval.</strong> Every verdict below is a "
      "<em>proposed</em> worksheet field pending human review and sign-off; "
      "the tool never approves.</p>")
    rp = result["rule_pack"]
    a("<p>Pack <b>%s</b> v%s \u00b7 sha256 <code>%s</code> \u00b7 status %s"
      % (_esc(rp["pack_id"]), _esc(rp["pack_version"]),
         _esc(rp["sha256"]), _esc(rp["status"])))
    a("<br>Run <code>%s</code> \u00b7 input <code>%s</code> \u00b7 engine %s"
      % (_esc(attestation["run_id"]), _esc(result["input_id"]),
         _esc(result["engine_version"])))
    a("<br>Network calls: none \u00b7 Deterministic: yes \u00b7 "
      "LLM invoked: none</p>")
    counts = attestation["verdict_counts"]
    a("<p>Proposed verdict counts: " + "; ".join(
        "%s %s (%s)" % (k, counts[k], GLOSS[k]) for k in
        ("compliant", "non_compliant", "doubtful", "out_of_coverage",
         "insufficient_input")) + "</p>")
    a("<h2>Worksheet rows</h2>")
    a("<table><thead><tr><th>Item</th><th>Domain</th>"
      "<th>Proposed verdict \u2014 tool</th>"
      "<th>Recorded verdict \u2014 reviewer</th>"
      "<th>Evidence</th></tr></thead><tbody>")
    for item in result["items"]:
        tok = item["verdict_proposed"]
        evrows = []
        for ev in item["evidence"]:
            trig = ev["trigger"]
            if trig["type"] == "term":
                where = "term %s \u201c%s\u201d code points %d\u2013%d" % (
                    _esc(trig["term_id"]), _esc(trig["match_text"]),
                    trig["start_offset"], trig["end_offset"])
            elif trig["type"] == "regex":
                where = "pattern <code>%s</code> \u201c%s\u201d [%d\u2013%d]" % (
                    _esc(trig["pattern"]), _esc(trig["match_text"]),
                    trig["start_offset"], trig["end_offset"])
            elif trig["type"] == "term_ref":
                where = "declared term %s (%s)" % (
                    _esc(trig["term_id"]), _esc(trig["surface_form"]))
            elif trig["type"] == "field_empty":
                where = "required field <b>%s</b> empty" % _esc(trig["field"])
            else:
                where = "field <b>%s</b> = %s" % (
                    _esc(trig["field"]), _esc(trig.get("value")))
            cits = "; ".join(
                "%s [%s]" % (_esc(cit_title[c]["title"]
                                 if c in cit_title else c),
                             ev["citation_status"])
                for c in ev["citation_ids"])
            rat = ev["rationale"]
            ar = rat.get("ar")
            evrows.append(
                "<p><b>%s</b> (%s, %s) \u2014 %s<br>Citations: %s<br>%s%s</p>"
                % (_esc(ev["rule_id"]), _esc(ev["outcome"]),
                   _esc(ev["severity"]), where, cits, _esc(rat["en"]),
                   ("<br><span class=\"ar\" dir=\"rtl\">%s</span>"
                    % _esc(ar)) if ar
                   else "<br><span class=\"gap\">AR gap \u2014 \u0641\u062c\u0648\u0629 "
                         "\u0639\u0631\u0628\u064a\u0629: no Arabic text in "
                         "source pack for this entry.</span>"))
        if not evrows:
            evrows.append("<p>No rule in this pack fired.</p>")
        if item["unverified_findings"]:
            evrows.append("<p><b>Unverified pathway:</b> %d finding(s) rest "
                          "on unverified citations; they can never produce a "
                          "Gap verdict.</p>"
                          % len(item["unverified_findings"]))
        a("<tr><td><b>%s</b><br>terms: %s<br>confirmed: %s</td><td>%s</td>"
          "<td><span class=\"badge\">Proposed: %s (%s)</span><br>limits: %s"
          "</td><td><span class=\"badge\">Recorded: not yet "
          "recorded</span></td><td>%s</td></tr>"
          % (_esc(item["item_ref"]),
             _esc("; ".join(item.get("term_ids", []))),
             "yes" if item["confirmed_by_operator"] else "no",
             _esc(item["domain_id"]), _esc(tok), _esc(GLOSS[tok]),
             _esc("; ".join(item.get("limits_applied", []))),
             "".join(evrows)))
    a("</tbody></table>")
    a("<h2>Coverage limits</h2><ol>")
    for code, en, ar in LIMITS:
        a("<li><b>%s</b> \u2014 %s<br><span class=\"ar\" dir=\"rtl\">%s</span>"
          "</li>" % (_esc(code), _esc(en), _esc(ar)))
    a("</ol>")
    a("<h2>Unverified sources (never requirements, never Gap)</h2><ul>")
    for u in pack["unverified_sources"]:
        a("<li><b>%s</b> \u2014 %s</li>"
          % (_esc(u["citation_id"]), _esc(u["reason"])))
    a("</ul>")
    a("<h2>Run attestation (read-only, embedded verbatim)</h2>")
    a("<pre>%s</pre>" % _esc(
        __import__("json").dumps(attestation, ensure_ascii=False, indent=2,
                                 sort_keys=True)))
    a("<div class=\"signoff\"><h2>Reviewer sign-off (human only \u2014 the "
      "tool leaves this blank)</h2>")
    a("<p>Reviewer name: ____________________ &nbsp; Role: "
      "____________________ &nbsp; Date: ____________</p>")
    a("<p>Statement: _______________________________________________</p>")
    a("<p>Signature: ____________________ &nbsp; Completed: no</p>")
    a("<p>Completed by the reviewer outside the tool \u2014 print or export "
      "this worksheet and fill it in. The tool can never fill these "
      "fields.</p></div>")
    a("</body></html>")
    return "\n".join(parts).encode("utf-8")
