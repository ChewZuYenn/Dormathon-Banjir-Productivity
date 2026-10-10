"""Local, single-active-job HTTP bridge. Standard library only, loopback only.
Start: python bridge/server.py --port 8765
GET /health, POST /jobs, GET /jobs/<id>, GET /jobs/<id>/result
No shell, arbitrary file paths, external networking or email delivery.
"""
import argparse
import copy
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
NAMES = ("Secretary", "Logistics", "Financial")
LIMIT = 1_000_000
LOCK = threading.Lock()
JOBS = {}
ORDER = deque()
UPSTREAM = "fdb1d58c8bd386a79c947c62f397dedc818a59f7"


def update(job_id, **kwargs):
    with LOCK:
        JOBS[job_id].update(kwargs)


def execute(job_id, request):
    directory = BASE / "runs" / job_id
    try:
        directory.mkdir(parents=True, exist_ok=False)
        input_path = directory / "request.json"
        input_path.write_text(json.dumps(request, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(BASE / "worker.py"), str(input_path), str(directory)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        errors = []
        def drain_errors():
            for line in process.stderr:
                if sum(map(len, errors)) < 20000:
                    errors.append(line)
        reader = threading.Thread(target=drain_errors, daemon=True)
        reader.start()
        def timeout():
            if process.poll() is None:
                process.kill()
        timer = threading.Timer(45, timeout)
        timer.start()
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                with LOCK:
                    job = JOBS[job_id]
                    if event.get("kind") == "status" and event.get("agent") in NAMES and event.get("status") in {"idle", "working", "done", "error"}:
                        job["agents"][event["agent"]] = {"status": event["status"], "step": event["step"]}
                        job["current_step"] = event["step"]
                        job["events"].append({"sequence": len(job["events"]), **event})
                    elif event.get("kind") == "result":
                        job["counts"] = event["counts"]
                        job["warnings"] = event["warnings"]
            return_code = process.wait()
            reader.join()
        finally:
            timer.cancel()
            process.stdout.close()
            process.stderr.close()
        if return_code != 0:
            (directory / "worker-error.txt").write_text("".join(errors), encoding="utf-8")
            raise RuntimeError("Agent 执行失败，请查看 bridge/runs 下 worker-error.txt；检查依赖与输入字段")
        update(job_id, status="done", current_step="本地代码验证完成；结果需人工检查", result_path=str(directory / "result.json"))
    except Exception as error:
        with LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(error)
            for agent in JOBS[job_id]["agents"].values():
                if agent["status"] == "working":
                    agent.update(status="error", step=str(error))
    finally:
        update(job_id, finished_at=time.time())


class Handler(BaseHTTPRequestHandler):
    def response(self, status, data):
        raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def allowed(self):
        # Deny browser cross-origin mutation and DNS-rebinding host names.
        host = self.headers.get("Host", "").split(":")[0]
        origin = self.headers.get("Origin")
        return host in {"127.0.0.1", "localhost"} and origin is None

    def do_GET(self):
        if not self.allowed():
            return self.response(403, {"error": "Loopback non-browser clients only"})
        if self.path == "/health":
            return self.response(200, {"status": "ok", "service": "office-agent-bridge", "version": 1, "upstream_commit": UPSTREAM,
                                       "modes": ["fixture", "records"], "ocr": False, "email_sending": False})
        match = re.fullmatch(r"/jobs/([0-9a-f]{32})(/result)?", self.path)
        if not match:
            return self.response(404, {"error": "Not found"})
        with LOCK:
            job = copy.deepcopy(JOBS.get(match[1]))
        if job is None:
            return self.response(404, {"error": "Unknown job (server restart clears in-memory jobs)"})
        result_path = job.pop("result_path", None)
        if match[2]:
            if job["status"] != "done" or result_path is None:
                return self.response(409, {"error": "Result not ready"})
            return self.response(200, json.loads(Path(result_path).read_text(encoding="utf-8")))
        return self.response(200, job)

    def do_POST(self):
        if not self.allowed():
            return self.response(403, {"error": "Loopback non-browser clients only"})
        if self.path != "/jobs":
            return self.response(404, {"error": "Not found"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.response(415, {"error": "application/json required"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= LIMIT:
                return self.response(413, {"error": "Body must be 1..1000000 bytes"})
            body = json.loads(self.rfile.read(size), parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Invalid numeric literal")))
            if not isinstance(body, dict) or body.get("mode") not in {"fixture", "records"}:
                raise ValueError("mode must be fixture or records")
            goal = body.get("goal", "")
            if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 500:
                raise ValueError("goal must be a non-empty string of at most 500 chars")
            request = {"mode": body["mode"], "goal": goal.strip()}
            if body["mode"] == "records":
                if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(body.get("period", ""))):
                    raise ValueError("period must be YYYY-MM; caller must prefilter records")
                from worker import validate_records
                validate_records(body.get("records"))
                request.update(period=body["period"], records=body["records"])
        except (ValueError, TypeError) as error:
            return self.response(400, {"error": str(error)})
        with LOCK:
            if any(j["status"] == "working" for j in JOBS.values()):
                return self.response(409, {"error": "A job is already running"})
            while len(ORDER) >= 30:
                JOBS.pop(ORDER.popleft(), None)  # Memory only; on-disk outputs are retained.
            job_id = uuid.uuid4().hex
            JOBS[job_id] = {"job_id": job_id, "status": "working", "mode": request["mode"], "goal": request["goal"],
                "current_step": "已接受本地任务", "created_at": time.time(), "events": [], "counts": {}, "warnings": [],
                "agents": {name: {"status": "idle", "step": "等待执行"} for name in NAMES}}
            ORDER.append(job_id)
        threading.Thread(target=execute, args=(job_id, request), daemon=True).start()
        self.response(202, {"job_id": job_id, "status": "working"})


def create_server(port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = create_server(args.port)
    print(f"Local Agent bridge ready at http://127.0.0.1:{server.server_port}; Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
