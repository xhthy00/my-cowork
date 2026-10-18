"""Snapshot official state before changing the shared dependency build."""
import json
import sqlite3
import time
from pathlib import Path
from runtime_contract import PROTOCOL_VERSION
from runtime_contract.environment import environment_identity


def prepare_state(directory: Path):
    manifest = directory / 'build-identity.json'
    current = {'protocol_version': PROTOCOL_VERSION, **environment_identity()}
    previous = json.loads(manifest.read_text()) if manifest.exists() else None
    if previous and previous.get('protocol_version') != PROTOCOL_VERSION:
        raise RuntimeError('Harness state protocol is incompatible; explicit migration is required')
    if previous and previous != current:
        snapshot = directory / 'upgrade-backups' / str(time.time_ns())
        snapshot.mkdir(parents=True)
        for name in ['runs.db', 'checkpoints.db']:
            source = directory / name
            if source.is_file():
                with sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True) as reader:
                    with sqlite3.connect(snapshot / name) as writer:
                        reader.backup(writer)
        (snapshot / 'build-identity.json').write_text(json.dumps(previous, indent=2))
    temporary = directory / 'build-identity.json.tmp'
    temporary.write_text(json.dumps(current, indent=2))
    temporary.replace(manifest)
