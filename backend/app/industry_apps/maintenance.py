"""Line-oriented desktop maintenance pipe, usable without a model or server."""
from __future__ import annotations

import json
import sys

from .lifecycle import Maintenance, operation, public_operation
from .package import app_root, inspect_update, list_installed
from .snapshots import checked_path
from .development import collect_development


def serve():
    root = app_root()
    session = None
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                command = request["command"]
                if command == "list":
                    result = {"apps": list_installed(root), "operation": public_operation(operation(root))}
                elif command == "inspect":
                    file = checked_path(__import__("pathlib").Path(request["file"]))
                    if file.stat().st_size > 50 * 1024 * 1024:
                        raise ValueError("ZIP exceeds 50 MiB")
                    result = inspect_update(file.read_bytes(), root)
                else:
                    if session is None:
                        session = Maintenance(root)
                    if command == "begin":
                        raw = None
                        if request["action"] in {"install", "develop"}:
                            file = checked_path(__import__("pathlib").Path(request["file"]))
                            if file.stat().st_size > 50 * 1024 * 1024:
                                raise ValueError("ZIP exceeds 50 MiB")
                            raw = file.read_bytes()
                        begun = session.begin(request["action"], request.get("app_id"), raw, request.get("sha256"))
                        result = begun if begun.get('unchanged') else public_operation(begun)
                    elif command == "prepare":
                        result = session.prepare()
                    elif command == "restore":
                        result = session.restore(request.get("error", ""))
                    elif command == "commit":
                        result = session.commit()
                    elif command == "cancel":
                        result = public_operation(session.cancel(keep_candidate=request.get("keep_candidate", False)))
                    elif command == "quarantine":
                        result = session.quarantine()
                    elif command == "retry":
                        result = session.retry(request["app_id"])
                    elif command == "disable_failed":
                        result = session.disable_failed(request["failures"])
                    elif command == "draining":
                        result = public_operation(session.save(operation(root), "draining"))
                    elif command == 'collect_development':
                        session.run_lock.acquire()
                        collect_development(root)
                        session.run_lock.close()
                        result = {'ok': True}
                    else:
                        raise ValueError("unknown maintenance command")
                response = {"ok": True, "result": result}
            except Exception as exc:
                response = {"ok": False, "error": str(exc)}
            print(json.dumps(response, ensure_ascii=False), flush=True)
    finally:
        if session:
            session.close()
