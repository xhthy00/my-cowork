"""Shared build identity using only standard-library package metadata."""
import hashlib
import importlib.metadata
from pathlib import Path

def environment_identity():
    lock = Path(__file__).resolve().parents[1] / 'uv.lock'
    return {
        'deepagents_version': importlib.metadata.version('deepagents'),
        'lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None,
    }
