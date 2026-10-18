"""Launch a sidecar with sys.executable; both processes share the same packages."""
import asyncio
import contextvars
import json
import logging
import os
import secrets
import socket
import sys
from contextlib import contextmanager
from pathlib import Path

import httpx
import uvicorn
from runtime_contract import PROTOCOL_VERSION
from runtime_contract.environment import environment_identity


_callback_context = contextvars.ContextVar('callback_listener', default=False)


class CallbackLogFilter(logging.Filter):
    def filter(self, record):
        # Desktop discovers the public backend port from uvicorn's logs.
        # Hide this private listener's INFO port without changing global levels.
        return not _callback_context.get() or record.levelno >= logging.WARNING


class CallbackServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # The backend owns process signals; its callback listener does not.
        yield


class RuntimeClient:
    def __init__(self, data_dir, broker, *, embedded_service=None, launch_command=None):
        self.data_dir = Path(data_dir)
        self.broker = broker
        self.embedded_service = embedded_service
        self.launch_command = launch_command
        self.process = self.http = self.broker_server = None
        self.broker_task = None
        self._start_lock = asyncio.Lock()
        self._log_filter = None

    async def start(self):
        async with self._start_lock:
            if self.http and self.process and self.process.returncode is not None:
                await self.close()
            if self.http or (self.embedded_service and self.embedded_service.saver):
                return
            if self.embedded_service:
                await self.embedded_service.start()
                return
            token, host_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            sock.listen(128)
            host_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
            self.broker_server = CallbackServer(uvicorn.Config(self.broker.app(host_token),
                log_config=None, log_level=None, access_log=False))
            self._log_filter = CallbackLogFilter()
            logging.getLogger('uvicorn.error').addFilter(self._log_filter)
            async def serve_callbacks():
                context = _callback_context.set(True)
                try:
                    await self.broker_server.serve(sockets=[sock])
                finally:
                    _callback_context.reset(context)
            self.broker_task = asyncio.create_task(serve_callbacks())
            cmd = self.launch_command or ([sys.executable, "--role=harness"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "cowork_harness.server"])
            child_env = dict(os.environ)
            child_env.pop("MY_COWORK_PARENT_PIPE", None)
            if getattr(sys, 'frozen', False):
                child_env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
            def debug(stage):
                if os.environ.get('MY_COWORK_HARNESS_DEBUG') == '1':
                    print('Harness startup: ' + stage, file=sys.stderr, flush=True)
            debug('spawning shared executable')
            self.process = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=None, env=child_env,
                cwd=str(Path(__file__).resolve().parents[2]))
            debug('child process created')
            bootstrap = {"token": token, "data_dir": str(self.data_dir / "harness"),
                         "host_url": host_url, "host_token": host_token}
            self.process.stdin.write((json.dumps(bootstrap) + "\n").encode())
            await self.process.stdin.drain()
            try:
                debug('bootstrap sent; waiting for readiness')
                ready = json.loads(await asyncio.wait_for(self.process.stdout.readline(), 30))
                debug('readiness received; checking health')
                self.http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{ready['port']}",
                    headers={"Authorization": "Bearer " + token}, timeout=None, trust_env=False)
                for _ in range(100):
                    if self.process.returncode is not None:
                        raise RuntimeError(f'Harness exited during startup: {self.process.returncode}')
                    try:
                        health = (await self.http.get("/v1/health", timeout=1)).json()
                        if health.get("protocol_version") != PROTOCOL_VERSION or not health.get("ready"):
                            raise RuntimeError("Harness protocol/readiness mismatch")
                        expected = environment_identity()
                        if any(health.get(key) != value for key, value in expected.items()):
                            raise RuntimeError('Host/harness shared dependency identity mismatch')
                        return
                    except httpx.TransportError as exc:
                        debug('health retry: ' + type(exc).__name__)
                        await asyncio.sleep(0.1)
                raise RuntimeError("Harness startup timed out")
            except BaseException:
                await self.close()
                raise

    async def submit(self, request):
        await self.start()
        if self.embedded_service:
            return await self.embedded_service.submit(request)
        result = await self.http.post("/v1/runs", json=request.model_dump())
        result.raise_for_status()
        return result.json()

    async def read(self, run_id):
        await self.start()
        if self.embedded_service:
            return self.embedded_service.store.get(run_id)
        result = await self.http.get(f"/v1/runs/{run_id}")
        result.raise_for_status()
        return result.json()

    async def events(self, run_id, after=0):
        await self.start()
        if self.embedded_service:
            while True:
                for event in self.embedded_service.store.events(run_id, after):
                    after = event["seq"]
                    yield event
                    if event["type"] == "graph.end":
                        return
                await asyncio.sleep(0.01)
        else:
            async with self.http.stream("GET", f"/v1/runs/{run_id}/events", params={"after": after}) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        yield json.loads(line[6:])

    async def resume(self, run_id, interrupt_id, value):
        if self.embedded_service:
            return await self.embedded_service.resume(run_id, interrupt_id, value)
        response = await self.http.post(f"/v1/runs/{run_id}/resume",
                                        json={"interrupt_id": interrupt_id, "value": value})
        response.raise_for_status()
        return response.json()

    async def history(self, run_id):
        if self.embedded_service:
            return self.embedded_service.store.events(run_id)
        response = await self.http.get(f'/v1/runs/{run_id}/history')
        response.raise_for_status()
        return response.json()['events']

    async def cancel(self, run_id):
        if self.embedded_service:
            return await self.embedded_service.cancel(run_id)
        if self.http:
            response = await self.http.post(f"/v1/runs/{run_id}/cancel")
            response.raise_for_status()
            return response.json()["cancelled"]
        return False

    async def close(self):
        if self.embedded_service:
            await self.embedded_service.close()
        if self.http:
            await self.http.aclose()
            self.http = None
        if self.process:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            self.process = None
        if self.broker_server:
            self.broker_server.should_exit = True
            await self.broker_task
            self.broker_server = None
        if self._log_filter:
            logging.getLogger('uvicorn.error').removeFilter(self._log_filter)
            self._log_filter = None
