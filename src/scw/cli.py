"""SCW command line. Offline; stdlib only.

  python3 -m scw run --pack PACK --input INPUT --outdir DIR [--run-started TS]
  python3 -m scw check-pack --pack PACK

`run` writes case-result.json, run-attestation.json, export.json
({case_result, run_attestation, input_status}), export.csv, export.html into DIR and prints
every file hash. --run-started pins the attestation clock so example runs are
byte-reproducible; without it the local wall clock is used (limit 7).
"""
import argparse
import datetime
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "..", "src"))

from scw import (ENGINE_VERSION, canon, check_pack_policy, dump_pretty,
                 evaluate, load_json, sha)
from scw import lite
from scw.attest import build_attestation
from scw.exports import build_csv, build_html
from scw.engine import assert_engine_compatible


def _utcnow():
    return (datetime.datetime.now(
        datetime.timezone.utc).replace(microsecond=0).isoformat()
        .replace("+00:00", "Z"))


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)
    h = hashlib.sha256(data).hexdigest()
    print("%s  %s" % (h, path))
    return h


def cmd_check_pack(args):
    pack = load_json(args.pack)
    errs = lite.check_pack(pack)
    if errs:
        print("STRUCT FAIL:")
        for e in errs:
            print("  " + e)
        return 1
    assert_engine_compatible(pack)
    pack_sha = check_pack_policy(pack)
    print("PACK OK  id=%s version=%s sha256=%s" % (
        pack["pack_id"], pack["pack_version"], pack_sha))
    return 0


def cmd_run(args):
    pack = load_json(args.pack)
    inp = load_json(args.input)
    errs = lite.check_pack(pack) + lite.check_input(inp)
    if errs:
        print("STRUCT FAIL:")
        for e in errs:
            print("  " + e)
        return 1
    started = args.run_started or _utcnow()
    result = evaluate(inp, pack)
    rerrs = lite.check_result(result)
    if rerrs:
        print("RESULT STRUCT FAIL:")
        for e in rerrs:
            print("  " + e)
        return 1
    pack_sha = sha(pack)
    csv_name = "scw-export-%s.csv" % (
        "run-%s-%s" % (started.replace("-", "").replace(":", ""),
                       sha(inp)[:8]))
    # CSV first: its hash embeds in the attestation (D9, no circularity).
    csv_bytes = build_csv(result, "run-%s-%s" % (
        started.replace("-", "").replace(":", ""), sha(inp)[:8]))
    csv_sha = hashlib.sha256(csv_bytes).hexdigest()
    finished = started if args.run_started else _utcnow()
    att = build_attestation(inp, result, pack_sha, started, finished,
                            csv_name, csv_sha, ENGINE_VERSION)
    aerrs = lite.check_attestation(att, input_sha=sha(inp),
                                   results_sha=sha(result),
                                   pack_sha=pack_sha,
                                   run_started=started)
    if aerrs:
        print("ATTESTATION STRUCT FAIL:")
        for e in aerrs:
            print("  " + e)
        return 1
    html_bytes = build_html(result, att, pack)
    os.makedirs(args.outdir, exist_ok=True)
    print("engine=%s pack_sha=%s" % (ENGINE_VERSION, pack_sha))
    hashes = {}
    hashes["case-result.json"] = _write(
        os.path.join(args.outdir, "case-result.json"),
        dump_pretty(result).encode("utf-8"))
    hashes["run-attestation.json"] = _write(
        os.path.join(args.outdir, "run-attestation.json"),
        dump_pretty(att).encode("utf-8"))
    hashes["export.json"] = _write(
        os.path.join(args.outdir, "export.json"),
        dump_pretty({"case_result": result,
                     "run_attestation": att,
                     # Standing export label, top-level bundle key
                     # only (closed case-result/attestation schemas
                     # untouched — UX contract).
                     "input_status": "unconfirmed input"}).encode("utf-8"))
    hashes["export.csv"] = _write(os.path.join(args.outdir, csv_name),
                                  csv_bytes)
    hashes["export.html"] = _write(os.path.join(args.outdir, "export.html"),
                                   html_bytes)
    print("run_id=%s" % att["run_id"])
    print("verdict_counts=%s" % att["verdict_counts"])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scw")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check-pack")
    p.add_argument("--pack", required=True)
    p.set_defaults(fn=cmd_check_pack)
    r = sub.add_parser("run")
    r.add_argument("--pack", required=True)
    r.add_argument("--input", required=True)
    r.add_argument("--outdir", required=True)
    r.add_argument("--run-started", default=None,
                   help="Pin run_started_utc (byte-reproducible examples).")
    r.set_defaults(fn=cmd_run)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
