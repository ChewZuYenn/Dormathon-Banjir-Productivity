import importlib.util
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bridge_server", BASE / "server.py")
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = server_module.create_server(0)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, body=None, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        request = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(), headers=h)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            return response.code, json.load(response)

    def test_health_and_errors(self):
        code, data = self.request("/health")
        self.assertEqual(code, 200)
        self.assertFalse(data["ocr"])
        self.assertEqual(self.request("/health", headers={"Origin": "https://example.org"})[0], 403)
        self.assertEqual(self.request("/jobs", {"goal": "test", "mode": "unknown"})[0], 400)
        self.assertEqual(self.request("/jobs", {"goal": "", "mode": "fixture"})[0], 400)
        self.assertEqual(self.request("/jobs", {"goal": "test", "mode": "records", "period": "2026-09", "records": [{}]})[0], 400)
        self.assertEqual(self.request("/jobs/" + "0" * 32)[0], 404)

    def test_real_fixture_pipeline(self):
        code, response = self.request("/jobs", {"mode": "fixture", "goal": "Close out September"})
        self.assertEqual(code, 202)
        job_id = response["job_id"]
        deadline = time.monotonic() + 40
        while True:
            code, job = self.request("/jobs/" + job_id)
            self.assertEqual(code, 200)
            if job["status"] != "working":
                break
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.05)
        self.assertEqual(job["status"], "done", job)
        self.assertTrue(all(item["status"] == "done" for item in job["agents"].values()))
        self.assertGreaterEqual(len(job["events"]), 8)
        code, result = self.request("/jobs/" + job_id + "/result")
        self.assertEqual(code, 200)
        self.assertEqual(result["counts"]["records"], 12)
        self.assertGreater(result["counts"]["exceptions"], 0)
        self.assertGreater(result["counts"]["tasks"], 0)
        self.assertTrue(all(email["status"] == "draft" for email in result["secretary"]["chase_emails"]))
        self.assertTrue(result["exception_mapping"])
        self.assertTrue(result["warnings"])
        print("REAL_AGENT_PIPELINE_TEST_PASS", result["counts"])
        # Test explicit pre-extracted-record input through the same real modules.
        record = result["records"][0]
        code, response = self.request("/jobs", {"mode": "records", "goal": "Check one pre-extracted test record", "period": "2026-09", "records": [record]})
        self.assertEqual(code, 202)
        deadline = time.monotonic() + 40
        while True:
            _, job = self.request("/jobs/" + response["job_id"])
            if job["status"] != "working":
                break
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.05)
        self.assertEqual(job["status"], "done", job)
        print("PREEXTRACTED_RECORD_TEST_PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
