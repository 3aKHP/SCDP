"""Official resource resolver and bounded decoder.

Resolver/XOR/gzip method adapted from Sallyn0225/eidolon-sc official_cdn.py,
commit 8cdb82b84670466041aed02640bb747f81ddca96, AGPL-3.0-or-later.
Modified 2026-11-10: strict paths, bounded expansion and explicit validation.
See THIRD_PARTY.md. No game content is included in this module.
"""
import hashlib
import json
import zlib
from pathlib import PurePosixPath
from .core import safe_path

ASSETS_URL = "https://shinycolors.enza.fun/assets"
XOR_KEY = b"B'KYWL[DI\\vqUIyw_we_are_hiring_https://knocknote.co.jp"


def asset_url(path, base=ASSETS_URL):
    file = PurePosixPath(safe_path(path))
    salt = file.stem[0] + file.stem[-1]
    return base.rstrip("/") + "/" + hashlib.sha256(f"{salt}/assets/{file}".encode()).hexdigest()


def manifest_url(base=ASSETS_URL):
    hashed = asset_url("asset-map.json", base).rsplit("/", 1)[-1]
    return base.rstrip("/") + "/asset-map-" + hashed


def xor(data):
    key = (XOR_KEY * (len(data) // len(XOR_KEY) + 1))[:len(data)]
    return (int.from_bytes(data) ^ int.from_bytes(key)).to_bytes(len(data))


def decode(path, data, limit=16 * 1024 * 1024):
    if not data:
        raise ValueError("empty_response")
    if data.lstrip().startswith((b"<", b"<!")):
        raise ValueError("maintenance_html")
    if not path.endswith((".json", ".atlas")):
        if len(data) > limit:
            raise ValueError("decoded_limit")
        return data
    compressed = xor(data)
    decoder = zlib.decompressobj(31)
    try:
        result = decoder.decompress(compressed, limit + 1)
        if len(result) > limit or decoder.unconsumed_tail:
            raise ValueError("decoded_limit")
        if decoder.unused_data:
            raise ValueError("trailing_data")
        if not decoder.eof and not compressed.endswith(b"\x00\x00\xff\xff"):
            raise ValueError("truncated_response")
    except zlib.error:
        raise ValueError("unknown_encoding") from None
    return result


def parse_json(data):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate_json_key")
            out[key] = value
        return out
    return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_json")))


def validate_story(data):
    value = parse_json(data)
    if not isinstance(value, list) or any(not isinstance(frame, dict) for frame in value):
        raise ValueError("unknown_story_structure")
    return value


def selected(path):
    return path.startswith("json/") and path.endswith(".json") and not path.startswith("json/support_skills/")


def classify(path):
    safe_path(path)
    if selected(path):
        return "story"
    if path.startswith("spine/"):
        return {".json": "spine.skeleton", ".atlas": "spine.atlas", ".png": "texture"}.get(PurePosixPath(path).suffix, "unknown")
    if path.startswith("images/"):
        return "image"
    if path.startswith("movies/"):
        return "video"
    if path.startswith("fonts/"):
        return "font"
    if path.startswith(("ae/", "particles/")):
        return "effect"
    if path.startswith("sounds/"):
        category = path.split("/")[1]
        return {"bgm": "audio.bgm", "se": "audio.se", "voice": "audio.voice"}.get(category, "audio.unknown")
    return "unknown"
