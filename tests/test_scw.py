#!/usr/bin/env python3
"""SCW test suite. Stdlib only: `python3 tests/test_scw.py`.

Maps to acceptance checks A1-A15 (proof obligations of this build):
 A1 determinism (byte-identical reruns)
 A2 golden vectors reproduced canonically (reference-vector identity 0.1.0)
 A3 offline structure (no network client in the runtime import graph)
 A4 no LLM in the runtime path
 A5 closed verdict set; non_compliant unreachable from starter pack
 A6 exact trigger evidence (offsets slice back; tamper rejected)
 A7 export binding (run_id + pack identity; CSV rebuild == attested hash)
 A8 blank sign-off (tool-filled sign-off fails; no code path fills it)
 A9 unverified exclusion (S2/S4 tamper gates fire)
 A10 bilingual pairs, logical-order Arabic, ar:null gap rendering
 A11 macOS offline run (this file IS the A11 evidence, stdlib only)
 A12 framing (proposal wording + limits present in HTML export)
 A13 citation quote contract (P7a-P7f: structural + S7 semantic gates)
 A14 single-offset-space normalization (NFD input slices back in NFC)
 A15 standing labels + no-default guided flow (source gates)
"""
import argparse
import copy
import csv
import io
import os
import re
import sys
import unicodedata
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))

from scw import (ENGINE_VERSION, REFERENCE_VECTOR_ENGINE_VERSION, canon,
                 check_pack_policy, evaluate, load_json, sha)
from scw import lite
from scw.attest import BLANK_SIGNOFF, build_attestation
from scw.exports import GLOSS, LIMITS, build_csv, build_html

PACK_PATH = os.path.join(BASE, "packs", "scw-qatar-starter.v0.1.0.json")
FIX = os.path.join(BASE, "tests", "fixtures")
PACK_SHA = "1ea71e863f05f7b8c1c2fd64ce0b58fd03de5a3512e25b15d4bee64451cae042"
GUIDED_SHA = ("5c14fdb761883ff70c6b1143dc51a29e088c28610e2f0805dbafe068c761ed87")
FREETEXT_SHA = ("64e34f3c23ee20637671508f78c2dd70d0b4aa60ae652c91a827d34405c84906")
GUIDED_CSV_SHA = ("92bb8f7f53089246a81820d0d5840b6d337cfd81011d20d734b9fdde538996d4")
FREETEXT_CSV_SHA = ("12f582c0585c6eec57d9a5a8e13cc778446e46c4c6cbf523455e2c0088b9822b")
TS = "2026-09-22T22:10:00Z"


def load_pack():
    return load_json(PACK_PATH)


def load_inp(name):
    return load_json(os.path.join(FIX, "case-input-%s.fixture.json" % name))


def load_res(name):
    return load_json(os.path.join(FIX, "case-result-%s.fixture.json" % name))


def load_att(name):
    return load_json(os.path.join(FIX,
                                  "run-attestation-%s.fixture.json" % name))


class GoldenVectors(unittest.TestCase):
    def test_pack_identity(self):
        self.assertEqual(sha(load_pack()), PACK_SHA)  # A7 binding

    def test_guided_vector(self):
        got = evaluate(load_inp("guided"), load_pack(),
                       engine_version=REFERENCE_VECTOR_ENGINE_VERSION)
        self.assertEqual(canon(got), canon(load_res("guided")))
        self.assertEqual(sha(got), GUIDED_SHA)  # A2

    def test_freetext_vector(self):
        got = evaluate(load_inp("freetext"), load_pack(),
                       engine_version=REFERENCE_VECTOR_ENGINE_VERSION)
        self.assertEqual(canon(got), canon(load_res("freetext")))
        self.assertEqual(sha(got), FREETEXT_SHA)  # A2

    def test_determinism(self):
        pack, inp = load_pack(), load_inp("freetext")
        self.assertEqual(canon(evaluate(inp, pack)),
                         canon(evaluate(inp, pack)))  # A1
        pack2, inp2 = load_pack(), load_inp("guided")
        self.assertEqual(canon(evaluate(inp2, pack2)),
                         canon(evaluate(inp2, pack2)))  # A1

    def test_live_engine_stamps_own_version(self):
        got = evaluate(load_inp("guided"), load_pack())
        self.assertEqual(got["engine_version"], ENGINE_VERSION)  # D10

    def test_guided_csv_rebuild_matches_golden(self):
        res = load_res("guided")
        att = load_att("guided")
        self.assertEqual(sha(build_csv(res, att["run_id"])),
                         GUIDED_CSV_SHA)  # A7
        self.assertEqual(att["exports"][0]["sha256"], GUIDED_CSV_SHA)

    def test_freetext_csv_rebuild_matches_golden(self):
        res = load_res("freetext")
        att = load_att("freetext")
        self.assertEqual(sha(build_csv(res, att["run_id"])),
                         FREETEXT_CSV_SHA)  # A7
        self.assertEqual(att["exports"][0]["sha256"], FREETEXT_CSV_SHA)


class OfflineNoLLM(unittest.TestCase):
    RUNTIME = ["canonical.py", "engine.py", "attest.py", "exports.py",
               "lite.py", "cli.py", "__init__.py", "__main__.py"]
    FORBIDDEN_TOP = {"socket", "urllib", "http", "requests", "ssl",
                     "openai", "anthropic", "transformers", "torch",
                     "tensorflow", "numpy", "subprocess"}

    def _imports_of(self, path):
        import ast
        with io.open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mods.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mods.add(node.module.split(".")[0])
        return mods

    def test_no_network_or_model_imports(self):
        srcdir = os.path.join(BASE, "src", "scw")
        for fname in self.RUNTIME:
            mods = self._imports_of(os.path.join(srcdir, fname))
            bad = mods & self.FORBIDDEN_TOP
            self.assertEqual(bad, set(), fname)  # A3/A4 O4

    def test_no_network_imports_at_runtime(self):
        import subprocess
        code = ("import sys; before=set(sys.modules); "
                "sys.path.insert(0, %r); import scw.cli; "
                "new=[m for m in sys.modules if m not in before]; "
                "print(' '.join(sorted(new)))" % os.path.join(BASE, "src"))
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, cwd=BASE)
        self.assertEqual(out.returncode, 0, out.stderr)
        new = set(out.stdout.split())
        bad = {m.split(".")[0] for m in new} & self.FORBIDDEN_TOP
        self.assertEqual(bad, set(), sorted(new))  # A3 structural


class Verdicts(unittest.TestCase):
    def test_closed_token_set_rejected(self):
        res = load_res("guided")
        bad = copy.deepcopy(res)
        bad["items"][0]["verdict_proposed"] = "approved"
        self.assertTrue(lite.check_result(bad))  # A5

    def test_non_compliant_unreachable_from_starter(self):
        pack = load_pack()
        for name in ("guided", "freetext"):
            res = evaluate(load_inp(name), pack)
            self.assertNotIn("non_compliant",
                             [i["verdict_proposed"] for i in res["items"]])
        self.assertFalse(any(r["outcome"] == "non_compliant"
                             for r in pack["rules"]))  # A5/D6

    def test_gloss_covers_all_tokens(self):
        self.assertEqual(sorted(GLOSS.keys()),
                         sorted(["compliant", "non_compliant", "doubtful",
                                 "out_of_coverage",
                                 "insufficient_input"]))  # UX gloss contract


class Evidence(unittest.TestCase):
    def test_offsets_slice_back(self):
        pack = load_pack()
        inp = load_inp("freetext")
        ntext = unicodedata.normalize("NFC", inp["free_text"]["text"])
        res = evaluate(inp, pack)
        n = 0
        for item in res["items"]:
            for ev in item["evidence"]:
                trig = ev["trigger"]
                if "start_offset" in trig:
                    self.assertEqual(
                        ntext[trig["start_offset"]:trig["end_offset"]],
                        trig["match_text"])
                    n += 1
        self.assertGreater(n, 0)  # A6

    def test_tampered_offset_detected(self):
        pack = load_pack()
        res = evaluate(load_inp("freetext"), pack)
        inp = load_inp("freetext")
        ntext = unicodedata.normalize("NFC", inp["free_text"]["text"])
        bad = copy.deepcopy(res)
        trig = bad["items"][0]["evidence"][0]["trigger"]
        trig["start_offset"] = trig["start_offset"] + 1
        ok = all(ntext[e["trigger"]["start_offset"]:
                       e["trigger"]["end_offset"]] == e["trigger"]
                 ["match_text"]
                 for i in bad["items"] for e in i["evidence"]
                 if "start_offset" in e["trigger"])
        self.assertFalse(ok)  # A6 tamper

    def test_evidence_ordering_field_empty_first(self):
        res = evaluate(load_inp("guided"), load_pack())
        item = next(i for i in res["items"]
                    if i["item_ref"] == "item-g-missing-cost")
        kinds = [e["trigger"]["type"] for e in item["evidence"]]
        self.assertIn("field_empty", kinds)  # engine rule R3
        self.assertEqual(kinds[0], "field_empty")


class ExportsAttestation(unittest.TestCase):
    def _run(self, name):
        pack, inp = load_pack(), load_inp(name)
        res = evaluate(inp, pack)
        run_id = "run-%s-%s" % (TS.replace("-", "").replace(":", ""),
                                sha(inp)[:8])
        csv_bytes = build_csv(res, run_id)
        att = build_attestation(inp, res, sha(pack), TS, TS,
                                "scw-export-%s.csv" % run_id,
                                sha(csv_bytes), ENGINE_VERSION)
        return pack, inp, res, att, csv_bytes, run_id

    def test_attestation_self_consistent(self):
        for name in ("guided", "freetext"):
            pack, inp, res, att, csv_bytes, run_id = self._run(name)
            self.assertEqual(lite.check_attestation(
                att, input_sha=sha(inp), results_sha=sha(res),
                pack_sha=sha(pack), run_started=TS), [])  # A7
            self.assertEqual(att["run_id"], run_id)
            counts = {k: 0 for k in
                      ("compliant", "non_compliant", "doubtful",
                       "out_of_coverage", "insufficient_input")}
            for i in res["items"]:
                counts[i["verdict_proposed"]] += 1
            self.assertEqual(att["verdict_counts"], counts)

    def test_attestation_reproduces_golden_vectors(self):
        for name in ("guided", "freetext"):
            pack, inp, exp_att = (load_pack(), load_inp(name),
                                  load_att(name))
            res = evaluate(
                inp, pack,
                engine_version=REFERENCE_VECTOR_ENGINE_VERSION)
            run_id = exp_att["run_id"]
            csv_bytes = build_csv(res, run_id)
            self.assertEqual(
                sha(csv_bytes), exp_att["exports"][0]["sha256"])  # D9
            att = build_attestation(
                inp, res, sha(pack), exp_att["run_started_utc"],
                exp_att["run_finished_utc"],
                exp_att["exports"][0]["filename"],
                exp_att["exports"][0]["sha256"],
                REFERENCE_VECTOR_ENGINE_VERSION)
            self.assertEqual(canon(att), canon(exp_att))  # A7 byte-level

    def test_csv_header_and_columns(self):
        pack, inp, res, att, csv_bytes, run_id = self._run("guided")
        text = csv_bytes.decode("utf-8")
        self.assertTrue(text.startswith("# SCW single-run CSV export v1\n"))
        self.assertNotIn("\r", text)
        rows = list(csv.reader(io.StringIO(text)))
        header = [r for r in rows if r and not r[0].startswith("#")][0]
        self.assertEqual(header, ["item_ref", "domain_id", "term_ids",
                                  "verdict_proposed",
                                  "confirmed_by_operator",
                                  "verdict_recorded", "rule_id", "outcome",
                                  "severity", "trigger_type", "match_text",
                                  "start_offset", "end_offset",
                                  "citation_ids", "citation_status",
                                  "rationale_en", "rationale_ar"])  # A7

    def test_signoff_blank_and_toolfill_rejected(self):
        pack, inp, res, att, csv_bytes, run_id = self._run("guided")
        self.assertEqual(att["reviewer_signoff"], BLANK_SIGNOFF)  # A8
        bad = copy.deepcopy(att)
        bad["reviewer_signoff"]["reviewer_name"] = "Auto Approved"
        self.assertTrue(lite.check_attestation(bad))  # A8 gate fires

    def test_html_framing_limits_disclaimer(self):
        pack, inp, res, att, csv_bytes, run_id = self._run("guided")
        page = build_html(res, att, pack).decode("utf-8")
        for phrase in ("Drafting aid only", "not legal advice",
                       "not a fatwa", "pending human review",
 "the tool never approves", "Completed: no",
                       "Reviewer sign-off (human only"):
            self.assertIn(phrase, page)  # A12
        for code, en, ar in LIMITS:
            self.assertIn(code, page)
            self.assertIn(en[:40], page)
        # Zero external resources and no link targets: no URL scheme at all.
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)

    def test_html_no_external_resources(self):
        pack, inp, res, att, csv_bytes, run_id = self._run("freetext")
        page = build_html(res, att, pack).decode("utf-8")
        self.assertNotRegex(page, r'<(script|link|img|iframe)[ >]')
        self.assertNotIn("url(", page)


class UnverifiedGates(unittest.TestCase):
    def test_s2_blocks_unverified_blocking(self):
        pack = load_pack()
        bad = copy.deepcopy(pack)
        bad["rules"][0]["outcome"] = "non_compliant"
        bad["rules"][0]["severity"] = "blocking"
        with self.assertRaises(ValueError) as ctx:
            check_pack_policy(bad)
        self.assertIn("S2", str(ctx.exception))  # A9

    def test_s4_unregistered_unverified(self):
        pack = load_pack()
        bad = copy.deepcopy(pack)
        bad["citations"].append({"citation_id": "cit-rogue",
                                 "status": "unverified",
                                 "title": "rogue",
                                 "url": "https://example.com",
                                 "fetch_date": "2026-09-22"})
        with self.assertRaises(ValueError) as ctx:
            check_pack_policy(bad)
        self.assertIn("S4", str(ctx.exception))  # A9

    def test_downgrade_mirror(self):
        res = evaluate(load_inp("freetext"), load_pack())
        for item in res["items"]:
            for ev in item["evidence"]:
                if ev["citation_status"] == "unverified":
                    self.assertIn(ev, item["unverified_findings"])  # R6 downgrade downgrade
            if item["unverified_findings"]:
                self.assertIn("advisory_only_unverified_citations",
                              item["limits_applied"])


class Bilingual(unittest.TestCase):
    def test_pack_pairs_and_gap_render(self):
        pack = load_pack()
        for d in pack["domains"]:
            self.assertTrue(d["label"]["en"])
            self.assertTrue(d["label"]["ar"])  # A10
        page = build_html(evaluate(load_inp("guided"), pack),
                          build_attestation(
                              load_inp("guided"),
                              evaluate(load_inp("guided"), pack),
                              sha(pack), TS, TS, "x.csv", "0" * 64,
                              ENGINE_VERSION), pack).decode("utf-8")
        self.assertIn('dir="rtl"', page)  # A10 logical-order AR blocks

    def test_arabic_offsets_code_points(self):
        pack = load_pack()
        inp = load_inp("freetext")
        ntext = unicodedata.normalize("NFC", inp["free_text"]["text"])
        res = evaluate(inp, pack)
        ar_evs = [e for i in res["items"] for e in i["evidence"]
                  if e["trigger"].get("term_id") == "term-murabaha"
                  and e["trigger"]["type"] == "term"
                  and e["trigger"]["surface_form"] == "مرابحة"]
        self.assertTrue(ar_evs)
        for ev in ar_evs:
            t = ev["trigger"]
            self.assertEqual(ntext[t["start_offset"]:t["end_offset"]],
                             "مرابحة")  # A6/A10 D5


class Refusals(unittest.TestCase):
    def test_pack_version_mismatch_refused(self):
        pack = load_pack()
        inp = load_inp("guided")
        bad = copy.deepcopy(inp)
        bad["rule_pack_ref"]["pack_version"] = "9.9.9"
        with self.assertRaises(ValueError):
            evaluate(bad, pack)

    def test_old_engine_refused(self):
        import scw.engine as eng
        pack = load_pack()
        old = eng.ENGINE_VERSION
        try:
            eng.ENGINE_VERSION = "0.0.1"
            with self.assertRaises(ValueError):
                evaluate(load_inp("guided"), pack)
        finally:
            eng.ENGINE_VERSION = old


class QuoteContract(unittest.TestCase):
    """A13: citation quote contract (probes P7a-P7f).

    Offline, stdlib-only. Structural path via lite.check_pack, semantic
    path (I-Q1/I-Q2/I-Q4, verified-contract) via check_pack_policy S7.
    """

    def _verifiable(self):
        pack = load_pack()
        bad = copy.deepcopy(pack)
        c = next(x for x in bad["citations"]
                 if x["citation_id"] == "cit-qcb-portal")
        c["status"] = "verified"
        c["sha256"] = "0" * 64
        c["quote"] = "Qatar Central Bank portal landing page."
        c["quote_sha256"] = sha_text(c["quote"])
        bad["unverified_sources"] = [
            u for u in bad["unverified_sources"]
            if u["citation_id"] != "cit-qcb-portal"]
        return bad

    def test_p7a_structural_verified_without_quote(self):
        bad = copy.deepcopy(load_pack())
        c = next(x for x in bad["citations"]
                 if x["citation_id"] == "cit-qcb-portal")
        c["status"] = "verified"  # no sha256/quote/quote_sha256
        errs = lite.check_pack(bad)
        self.assertTrue(any("citations[2]" in e and "verified" in e
                            for e in errs), errs)  # P7a STRUCT FAIL

    def test_p7b_semantic_quote_hash_mismatch(self):
        bad = self._verifiable()
        c = next(x for x in bad["citations"]
                 if x["citation_id"] == "cit-qcb-portal")
        c["quote_sha256"] = "1" * 64
        self.assertEqual(lite.check_pack(bad), [])
        with self.assertRaises(ValueError) as ctx:
            check_pack_policy(bad)
        self.assertIn("S7: quote-integrity violation: cit-qcb-portal",
                      str(ctx.exception))  # P7b

    def test_p7c_semantic_nfd_quote_rejected(self):
        bad = self._verifiable()
        c = next(x for x in bad["citations"]
                 if x["citation_id"] == "cit-qcb-portal")
        c["quote"] = unicodedata.normalize("NFD", "café")
        c["quote_sha256"] = sha_text(c["quote"])
        self.assertEqual(lite.check_pack(bad), [])
        with self.assertRaises(ValueError) as ctx:
            check_pack_policy(bad)
        self.assertIn("S7: quote-integrity violation: cit-qcb-portal",
                      str(ctx.exception))  # P7c I-Q1

    def test_p7d_semantic_verified_missing_sha(self):
        bad = self._verifiable()
        c = next(x for x in bad["citations"]
                 if x["citation_id"] == "cit-qcb-portal")
        del c["sha256"]
        with self.assertRaises(ValueError) as ctx:
            check_pack_policy(bad)
        self.assertIn("S7: verified-citation-missing-quote-contract",
                      str(ctx.exception))  # P7d

    def test_p7e_positive_wellformed_verified(self):
        good = self._verifiable()
        self.assertEqual(lite.check_pack(good), [])
        pack_sha = check_pack_policy(good)
        self.assertRegex(pack_sha, r"^[a-f0-9]{64}$")  # P7e PACK OK

    def test_p7f_pairing_unverified_half_pair(self):
        bad = copy.deepcopy(load_pack())
        c = next(x for x in bad["citations"]
                 if x["citation_id"] == "cit-qcb-portal")
        c["quote"] = "orphan quote, no hash"
        errs = lite.check_pack(bad)
        self.assertTrue(any("quote/quote_sha256" in e for e in errs),
                        errs)  # P7f


def sha_text(s):
    import hashlib
    return hashlib.sha256(
        unicodedata.normalize("NFC", s).encode("utf-8")).hexdigest()


class NormalizationOffsets(unittest.TestCase):
    """A14: normalize once, match and slice in one offset space."""

    def test_nfd_input_offsets_slice_nfc(self):
        pack = load_pack()
        inp = load_inp("freetext")
        bad = copy.deepcopy(inp)
        # NFD combining mark BEFORE every match: raw-text offsets would
        # all shift by one; NFC-space offsets must still slice back.
        bad["free_text"]["text"] = ("cafe" + chr(0x301) +
                                       " interest and murabaha مرابحة")
        ntext = unicodedata.normalize("NFC", bad["free_text"]["text"])
        self.assertNotEqual(bad["free_text"]["text"], ntext)
        res = evaluate(bad, pack)
        kinds = set()
        n = 0
        for item in res["items"]:
            for ev in item["evidence"]:
                trig = ev["trigger"]
                if "start_offset" in trig:
                    self.assertEqual(
                        ntext[trig["start_offset"]:trig["end_offset"]],
                        trig["match_text"])
                    kinds.add(trig["type"])
                    n += 1
        self.assertGreater(n, 0)
        self.assertIn("regex", kinds)  # interest fires in NFC space
        self.assertIn("term", kinds)  # murabaha fires in NFC space


class StandingLabels(unittest.TestCase):
    """A15: every export carries the standing unconfirmed label."""

    def test_csv_label_row(self):
        pack, inp, res, att, csv_bytes, run_id = \
            ExportsAttestation()._run("guided")
        lines = csv_bytes.decode("utf-8").split("\n")
        self.assertIn("# input_status,unconfirmed input", lines)
        pos = lines.index("# input_status,unconfirmed input")
        sha_pos = next(i for i, l in enumerate(lines)
                       if l.startswith("# results_sha256"))
        head_pos = next(i for i, l in enumerate(lines)
                        if l.startswith("item_ref,"))
        self.assertEqual(pos, sha_pos + 1)  # label position
        self.assertEqual(head_pos, pos + 1)

    def test_html_label_block(self):
        pack, inp, res, att, csv_bytes, run_id = \
            ExportsAttestation()._run("guided")
        page = build_html(res, att, pack).decode("utf-8")
        low = page.lower()
        self.assertIn("input status: unconfirmed input", low)
        self.assertIn("مدخلات غير مؤكدة", page)
        self.assertLess(page.index("Input status: unconfirmed input"),
                        page.index("<h2"))  # label position

    def test_json_label_via_run(self):
        import tempfile
        from scw import cli as scw_cli
        pack, inp = load_pack(), load_inp("guided")
        with tempfile.TemporaryDirectory() as d:
            args = argparse.Namespace(
                pack=os.path.join(BASE, "packs",
                                  "scw-qatar-starter.v0.1.0.json"),
                input=os.path.join(FIX, "case-input-guided.fixture.json"),
                outdir=d, run_started=TS)
            self.assertEqual(scw_cli.cmd_run(args), 0)
            bundle = load_json(os.path.join(d, "export.json"))
            self.assertEqual(bundle["input_status"],
                             "unconfirmed input")  # label present
            self.assertIn("case_result", bundle)
            self.assertIn("run_attestation", bundle)
            csv_raw = io.open(
                os.path.join(d, bundle["run_attestation"]["exports"][0]
                             ["filename"]), encoding="utf-8").read()
            self.assertIn("# input_status,unconfirmed input",
                          csv_raw.split("\n"))
            html_raw = io.open(os.path.join(d, "export.html"),
                               encoding="utf-8").read()
            self.assertIn("Input status: unconfirmed input", html_raw)

    def test_export_fence_no_reviewed_claim(self):
        pack, inp, res, att, csv_bytes, run_id = \
            ExportsAttestation()._run("freetext")
        page = build_html(res, att, pack).decode("utf-8")
        for blob in (page, csv_bytes.decode("utf-8")):
            low = blob.lower()
            self.assertNotIn("reviewed worksheet", low)  # export fence
            self.assertIsNone(re.search(r"status\s*:\s*reviewed", low))


class GuidedNoDefault(unittest.TestCase):
    """A15: no default term selection; refusal gate copy (static).

    DOM behaviour (guided-flow probes) is driven by tools/dom_evidence.py against
    the real app; these static gates pin the UI-script source contract.
    """

    def _ui_script(self):
        with io.open(os.path.join(BASE, "app", "index.html"),
                     encoding="utf-8") as f:
            html = f.read()
        # The UI script is the script element AFTER the </script> that
        # closes <script id="pack"> (static-gate scope).
        return html.split("</script>")[2]

    def test_no_default_term_injection(self):
        ui = self._ui_script()
        self.assertEqual(ui.count("terms.length ? terms"), 0)  # no-default gate
        self.assertEqual(ui.count('terms: ["term-murabaha"]'), 0)  # no-preselect gate
        self.assertEqual(ui.count("term-murabaha"), 0)  # zero mentions

    def test_gate_helper_copy_and_alert(self):
        ui = self._ui_script()
        for s in ("Select at least one structure term",
                  "لن تختار الورقة أي مصطلح نيابة عنك",
                  "no structure term selected — check at least one term",
                  "The workbook will not choose one for you.",
                  "لم يُختَر أي مصطلح بنية",
                  "Remove item / حذف البند",
                  "data-statuslabel",
                  "Input status: unconfirmed input",
                  "مدخلات غير مؤكدة"):
            self.assertIn(s, ui)
        with io.open(os.path.join(BASE, "app", "index.html"),
                     encoding="utf-8") as f:
            html = f.read()
        self.assertIn('<p id="runwarn" role="alert">', html)
        self.assertIn('id="statuslabel"', html)
        # App pack identity pin tracks the migrated pack.
        m = re.search(r'var PACK_SHA = "([a-f0-9]{64})";', html)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), sha(load_pack()))
        self.assertNotIn("fatf", ui)
        self.assertNotIn("FATF", ui)


if __name__ == "__main__":
    unittest.main(verbosity=2)
