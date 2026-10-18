"""Exercise the real frozen backend -> same-executable harness startup path."""
import argparse
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request


def stop_backend(proc, reader):
    if proc.poll() is None:
        if sys.platform == 'win32':
            # Popen.terminate() only kills the host on Windows. Its harness can
            # still hold SQLite files when TemporaryDirectory tries to delete
            # them, so stop the owned process tree before cleaning up.
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    # Descendants inherit stderr, redirected to this pipe. EOF confirms their
    # handles have closed too; waiting for the host alone is insufficient.
    reader.join(timeout=10)
    if reader.is_alive():
        raise RuntimeError('Backend subprocesses did not release their log pipe')
    proc.stdout.close()


def main(binary):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / 'mcp.json').write_text('{}')
        env = {**os.environ,
            'MY_COWORK_DATA_DIR': str(root / 'data'),
            'MY_COWORK_INDUSTRY_APPS_ROOT': str(root / 'apps'),
            'MY_COWORK_CHANNELS_DB': str(root / 'channels.db'),
            'MY_COWORK_MCP_JSON': str(root / 'mcp.json'),
            'MY_COWORK_ENABLE_SCHEDULER': '0', 'MY_COWORK_CHANNEL_AUTOSTART': '0',
            'PYTHONUNBUFFERED': '1', 'MY_COWORK_HARNESS_DEBUG': '1'}
        env.pop('MY_COWORK_PARENT_PIPE', None)
        # Exercise a clean install, without inherited model configuration.
        for key in ('MY_COWORK_API_KEY', 'MY_COWORK_PROVIDER', 'MY_COWORK_MODEL',
                    'MY_COWORK_BASE_URL', 'MY_COWORK_FALLBACK',
                    'OPENAI_API_KEY', 'ANTHROPIC_API_KEY'):
            env.pop(key, None)
        proc = subprocess.Popen([str(binary.resolve()), '--port', '0'], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        lines = queue.Queue()
        log = []
        def read():
            for line in proc.stdout:
                lines.put(line)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                try:
                    line = lines.get(timeout=.2)
                    log.append(line)
                    if line.startswith('Harness '):
                        print(line.strip(), flush=True)
                except queue.Empty:
                    if proc.poll() is not None:
                        raise RuntimeError('Frozen backend exited: ' + ''.join(log)[-5000:])
                    continue
                match = re.search(r'127\.0\.0\.1:(\d+)', line)
                if not match:
                    continue
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{match[1]}/health', timeout=2) as response:
                        assert json.load(response)['status'] == 'ok'
                    # Readiness is emitted only after lifespan starts the harness
                    # and checks its dependency identity and SQLite saver.
                    assert (root / 'data/harness/checkpoints.db').is_file()
                    break
                except (OSError, AssertionError):
                    continue
            else:
                raise TimeoutError('Frozen backend readiness timed out: ' + ''.join(log)[-5000:])
        finally:
            stop_backend(proc, reader)
    print('FROZEN BACKEND SMOKE OK: no model configured, backend -> same executable harness, joint readiness and cleanup')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, required=True)
    main(parser.parse_args().binary)
