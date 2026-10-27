"""Authenticated loopback HTTP/SSE server, launched with the shared interpreter."""
import asyncio
import hashlib
import importlib.metadata
import json
import os
import secrets
import socket
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from runtime_contract import RunRequest, ResumeRequest, PROTOCOL_VERSION
from .service import RuntimeService
from runtime_contract.environment import environment_identity


def create_app(service, token):
    @asynccontextmanager
    async def lifespan(app):
        await service.start()
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def authorize(request: Request, call_next):
        from starlette.responses import JSONResponse
        if request.client and request.client.host not in {"127.0.0.1", "::1"}:
            return JSONResponse({"detail": "Loopback only"}, status_code=403)
        if request.headers.get("origin") or not secrets.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + token):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/v1/health")
    async def health():
        return {"status": "ok", "protocol_version": PROTOCOL_VERSION,
                **environment_identity(),
                "python": sys.executable, "ready": service.saver is not None}

    @app.post("/v1/runs")
    async def submit(body: RunRequest):
        try:
            return await service.submit(body)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/v1/runs/{run_id}")
    async def read(run_id: str):
        row = service.store.get(run_id)
        if not row:
            raise HTTPException(404, "Unknown run")
        return {key: row[key] for key in ("id", "status", "pending", "request")}

    @app.get("/v1/runs/{run_id}/events")
    async def events(run_id: str, request: Request, after: int = 0):
        if not service.store.get(run_id):
            raise HTTPException(404, "Unknown run")
        async def stream():
            cursor = after
            heartbeat = asyncio.get_running_loop().time()
            while not await request.is_disconnected():
                rows = service.store.events(run_id, cursor)
                for event in rows:
                    cursor = event["seq"]
                    yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event["type"] == "graph.end":
                        return
                now = asyncio.get_running_loop().time()
                if now - heartbeat >= 10:
                    yield ': keepalive\n\n'
                    heartbeat = now
                await asyncio.sleep(0.1)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get('/v1/runs/{run_id}/history')
    async def history(run_id: str):
        if not service.store.get(run_id):
            raise HTTPException(404, 'Unknown run')
        return {'events': service.store.events(run_id)}

    @app.post("/v1/runs/{run_id}/resume")
    async def resume(run_id: str, body: ResumeRequest):
        try:
            return await service.resume(run_id, body.interrupt_id, body.value)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/v1/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        return {"cancelled": await service.cancel(run_id)}

    @app.post("/v1/drain")
    async def drain():
        service.draining = True
        return {"ok": True}
    return app


def main():
    import uvicorn
    bootstrap = json.loads(sys.stdin.readline())
    token = bootstrap["token"]
    service = RuntimeService(bootstrap["data_dir"], host_url=bootstrap["host_url"],
                             host_token=bootstrap["host_token"])
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    print(json.dumps({"port": sock.getsockname()[1], "protocol_version": 1}), flush=True)
    server = uvicorn.Server(uvicorn.Config(create_app(service, token), log_level="warning"))
    async def serve():
        loop = asyncio.get_running_loop()
        def parent_watch():
            # EOF gracefully checkpoints/terminates work and prevents orphans.
            while os.read(sys.stdin.fileno(), 1):
                pass
            loop.call_soon_threadsafe(setattr, server, 'should_exit', True)
        threading.Thread(target=parent_watch, daemon=True).start()
        await server.serve(sockets=[sock])
    asyncio.run(serve())


if __name__ == "__main__":
    main()
