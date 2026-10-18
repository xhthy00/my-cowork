"""Start the actual shared-environment sidecar without contacting a model provider."""
import argparse
import asyncio
import importlib.metadata
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.host_capabilities.broker import CapabilityBroker
from app.observability.trace import TraceBus
from app.runtime_client.client import RuntimeClient


async def main(binary=None):
    with tempfile.TemporaryDirectory() as folder:
        broker = CapabilityBroker(folder, TraceBus())
        client = RuntimeClient(folder, broker, launch_command=[str(binary), "--role=harness"] if binary else None)
        try:
            await client.start()
            response = await client.http.get('/v1/health')
            response.raise_for_status()
            health = response.json()
            assert Path(health['python']).resolve() == Path(binary or sys.executable).resolve()
            assert health['deepagents_version'] == importlib.metadata.version('deepagents')
            assert health['ready'] and health['protocol_version'] == 1
            unauthorized = await client.http.get('/v1/health', headers={'Authorization': 'Bearer invalid'})
            assert unauthorized.status_code == 401
            print('HARNESS SMOKE OK: shared Python environment, authenticated sidecar, persistent checkpoint')
        finally:
            await client.close()
            broker.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.binary))
