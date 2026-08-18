"""WeChat iLink outbound media helpers (AES-128-ECB CDN upload)."""

from __future__ import annotations

import base64
import hashlib
import math
import os

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

AES_BLOCK = 16
MEDIA_TYPE_FILE = 3
FILE_MAX_BYTES = 20 * 1024 * 1024
FILE_MAX_COUNT = 5
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
WEIXIN_CDN_TIMEOUT = 120.0


def ciphertext_size(rawsize: int) -> int:
    """PKCS7 ciphertext length: always at least one padding byte."""
    return math.ceil((max(0, int(rawsize)) + 1) / AES_BLOCK) * AES_BLOCK


def aes128_ecb_pkcs7(plaintext: bytes, key16: bytes) -> bytes:
    if len(key16) != AES_BLOCK:
        raise ValueError("AES key must be 16 bytes")
    cipher = AES.new(key16, AES.MODE_ECB)
    return cipher.encrypt(pad(plaintext, AES_BLOCK))


def aes128_ecb_decrypt(ciphertext: bytes, key16: bytes) -> bytes:
    if len(key16) != AES_BLOCK:
        raise ValueError("AES key must be 16 bytes")
    cipher = AES.new(key16, AES.MODE_ECB)
    return unpad(cipher.decrypt(ciphertext), AES_BLOCK)


def aeskey_hex(key16: bytes) -> str:
    if len(key16) != AES_BLOCK:
        raise ValueError("AES key must be 16 bytes")
    return key16.hex()


def aes_key_for_send(key16: bytes) -> str:
    """OpenClaw outbound file aes_key: base64(hex ASCII), not base64(raw bytes)."""
    return base64.b64encode(aeskey_hex(key16).encode("ascii")).decode("ascii")


def random_aes_key() -> bytes:
    return os.urandom(AES_BLOCK)


def random_filekey() -> str:
    return os.urandom(AES_BLOCK).hex()


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()
