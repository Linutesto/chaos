from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Dict, Any, List


def _pbkdf2_key(passphrase: str, salt: bytes, length: int = 32, rounds: int = 200_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, rounds, dklen=length)


def _keystream_block(key: bytes, salt: bytes, counter: int) -> bytes:
    msg = salt + counter.to_bytes(8, "big")
    return hmac.new(key, msg, hashlib.sha256).digest()


def _xor_stream(data: bytes, key: bytes, salt: bytes, start_counter: int = 0) -> bytes:
    out = bytearray(len(data))
    i = 0
    counter = start_counter
    while i < len(data):
        block = _keystream_block(key, salt, counter)
        counter += 1
        n = min(len(block), len(data) - i)
        for j in range(n):
            out[i + j] = data[i + j] ^ block[j]
        i += n
    return bytes(out)


def _chunk_fractal(data: bytes, depth: int, fanout: int) -> List[bytes]:
    # Split data into fanout^depth chunks as evenly as possible
    chunks: List[bytes] = []
    total = len(data)
    parts = max(1, fanout ** max(0, depth))
    base = total // parts
    rem = total % parts
    start = 0
    for i in range(parts):
        size = base + (1 if i < rem else 0)
        chunks.append(data[start:start + size])
        start += size
    return chunks


def fractal_encrypt(obj: Dict[str, Any], passphrase: str, *, depth: int = 2, fanout: int = 3) -> Dict[str, Any]:
    raw = (repr(obj) if not isinstance(obj, dict) else None)
    # We expect a dict; serialize using JSON-like repr via utf-8 JSON dump semantics in caller
    import json
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    salt = os.urandom(16)
    key = _pbkdf2_key(passphrase, salt)
    chunks = _chunk_fractal(data, depth, fanout)
    c_blocks: List[str] = []
    for i, ch in enumerate(chunks):
        ct = _xor_stream(ch, key, salt, start_counter=i)
        c_blocks.append(base64.b64encode(ct).decode("ascii"))
    mac = hmac.new(key, b"".join(base64.b64decode(b) for b in c_blocks), hashlib.sha256).digest()
    env = {
        "format": "QJSON-FE-v1",
        "params": {"depth": depth, "fanout": fanout},
        "salt": base64.b64encode(salt).decode("ascii"),
        "blocks": c_blocks,
        "mac": base64.b64encode(mac).decode("ascii"),
    }
    return env


def fractal_decrypt(env: Dict[str, Any], passphrase: str) -> Dict[str, Any]:
    import json
    if not isinstance(env, dict) or env.get("format") != "QJSON-FE-v1":
        raise ValueError("Not a QJSON-FE-v1 envelope")
    salt = base64.b64decode(env.get("salt", ""))
    if not salt:
        raise ValueError("Missing salt")
    key = _pbkdf2_key(passphrase, salt)
    blocks_b64 = env.get("blocks") or []
    ct_concat = b"".join(base64.b64decode(b) for b in blocks_b64)
    mac = base64.b64decode(env.get("mac", ""))
    if not hmac.compare_digest(mac, hmac.new(key, ct_concat, hashlib.sha256).digest()):
        raise ValueError("Integrity check failed (MAC mismatch)")
    # Decrypt each block
    pt_parts: List[bytes] = []
    for i, b64 in enumerate(blocks_b64):
        ct = base64.b64decode(b64)
        pt = _xor_stream(ct, key, salt, start_counter=i)
        pt_parts.append(pt)
    data = b"".join(pt_parts)
    return json.loads(data.decode("utf-8"))

# Disclaimer: This module provides an experimental, non-standard encryption scheme
# built from standard primitives (PBKDF2-HMAC, HMAC-SHA256, and a stream XOR). It
# is not a substitute for vetted cryptographic libraries. Use for obfuscation or
# research only. For real security, integrate a standard AEAD (e.g., AES-GCM) via
# a well-maintained crypto library.

