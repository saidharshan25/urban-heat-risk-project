"""Unit tests for Agent API health monitoring, failure states, and recovery."""

import json
import socket
import unittest
import urllib.request
import urllib.error
import threading
import time
from http.server import ThreadingHTTPServer

from src.dashboard.agent_api import AgentAPIHandler, HOST


class TestAgentAPIHealthAndRecovery(unittest.TestCase):
    """Test suite for Agent API health checks, failure handling, and recovery."""

    def test_successful_health_check(self):
        """Verify successful health check returns 200 with required status fields."""
        server = ThreadingHTTPServer((HOST, 0), AgentAPIHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            url = f"http://{HOST}:{port}/api/agent/health"
            req = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1:8080"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data.get("status"), "ok")
                self.assertIn("service", data)
                self.assertIn("external_notifications_enabled", data)
                self.assertFalse(data["external_notifications_enabled"])
                self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:8080")
        finally:
            server.shutdown()
            server.server_close()

    def test_api_failure_when_server_offline(self):
        """Verify client handles unreachable server gracefully with connection error without freezing."""
        # Find an unused ephemeral port that is not listening
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((HOST, 0))
        closed_port = sock.getsockname()[1]
        sock.close()

        url = f"http://{HOST}:{closed_port}/api/agent/health"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.URLError) as ctx:
            urllib.request.urlopen(req, timeout=1)
        err_msg = str(ctx.exception).lower()
        self.assertTrue(any(term in err_msg for term in ["refused", "timed out", "winerror", "10061"]))

    def test_api_recovery_after_restart(self):
        """Verify health check recovers automatically once the server comes back online."""
        # Phase 1: Server running
        server = ThreadingHTTPServer((HOST, 0), AgentAPIHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        url = f"http://{HOST}:{port}/api/agent/health"
        with urllib.request.urlopen(url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)

        # Phase 2: Server shut down (simulating temporary failure)
        server.shutdown()
        server.server_close()
        time.sleep(0.1)

        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(url, timeout=1)

        # Phase 3: Server restarted on same port (recovery)
        new_server = ThreadingHTTPServer((HOST, port), AgentAPIHandler)
        new_thread = threading.Thread(target=new_server.serve_forever, daemon=True)
        new_thread.start()

        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data.get("status"), "ok")
        finally:
            new_server.shutdown()
            new_server.server_close()

    def test_cors_options_preflight(self):
        """Verify CORS preflight OPTIONS request returns 204 with allowed headers."""
        server = ThreadingHTTPServer((HOST, 0), AgentAPIHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            url = f"http://{HOST}:{port}/api/agent/health"
            req = urllib.request.Request(
                url,
                headers={"Origin": "http://127.0.0.1:8080"},
                method="OPTIONS",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 204)
                self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:8080")
                self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
