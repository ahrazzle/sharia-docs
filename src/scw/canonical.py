"""SCW canonical JSON + sha256 (LOCKED, architecture decision D4).

canonical(obj) = json.dumps(obj, sort_keys=True, ensure_ascii=False,
separators=(",", ":")).encode("utf-8") over NFC-normalized strings.
sha256 is taken over those bytes. The pack/result/input identity.
"""
import hashlib
import json
import unicodedata


def _nfc(obj):
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, list):
        return [_nfc(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _nfc(v) for k, v in obj.items()}
    return obj


def canon(obj):
    return json.dumps(_nfc(obj), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def sha(obj_or_bytes):
    if isinstance(obj_or_bytes, (bytes, bytearray)):
        return hashlib.sha256(bytes(obj_or_bytes)).hexdigest()
    return hashlib.sha256(canon(obj_or_bytes)).hexdigest()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_pretty(obj):
    return json.dumps(_nfc(obj), ensure_ascii=False, indent=2) + "\n"
