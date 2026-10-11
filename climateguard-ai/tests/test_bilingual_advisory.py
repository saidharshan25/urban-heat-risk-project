"""Unit tests for Bilingual (English / Tamil) Advisory generation in ClimateGuard AI."""

import json
import unittest
import urllib.request
import urllib.error
import threading
import time
from http.server import ThreadingHTTPServer

from src.dashboard.agent_api import AgentAPIHandler, HOST, load_report, REPORT_PATH


class TestBilingualAdvisory(unittest.TestCase):
    """Test suite for English and Tamil bilingual advisory generation."""

    @classmethod
    def setUpClass(cls):
        # Bind AgentAPIHandler to ephemeral port on loopback
        cls.server = ThreadingHTTPServer((HOST, 0), AgentAPIHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post_json(self, endpoint: str, payload: dict) -> tuple[int, dict]:
        url = f"http://{HOST}:{self.port}{endpoint}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Origin": "http://127.0.0.1:8080",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read().decode("utf-8"))
            return exc.code, data

    def test_default_advisory_is_english(self):
        """Verify default language when omitted is English."""
        status, data = self._post_json("/api/agent/advisory", {"scenario": "heatwave"})
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["language"], "en")
        self.assertIn("ClimateGuard AI precautionary advisory", data["advisory"])
        self.assertIn("official weather alert", data["disclaimer"])

    def test_explicit_english_advisory(self):
        """Verify explicit language='en' returns English advisory content."""
        status, data = self._post_json("/api/agent/advisory", {
            "scenario": "extreme_heat",
            "language": "en"
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["language"], "en")
        self.assertEqual(data["scenario"], "Extreme heat")
        self.assertIn("heat-safety measures", data["advisory"])

    def test_tamil_advisory_content(self):
        """Verify explicit language='ta' returns authentic Tamil advisory content."""
        status, data = self._post_json("/api/agent/advisory", {
            "scenario": "heatwave",
            "language": "ta"
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["language"], "ta")
        # Verify genuine Tamil script in advisory
        self.assertIn("முன்னெச்சரிக்கை", data["advisory"])
        self.assertIn("அதிகாரப்பூர்வ", data["advisory"])
        self.assertIn("தண்ணீர் குடிக்கவும்", data["advisory"])
        # Verify genuine Tamil script in disclaimer
        self.assertIn("ஆரம்பகட்ட தகவல் ஆலோசனை", data["disclaimer"])
        self.assertFalse(data["official_warning"])

    def test_invalid_language_rejected(self):
        """Verify unsupported language code is rejected with 400 status."""
        status, data = self._post_json("/api/agent/advisory", {
            "scenario": "heatwave",
            "language": "fr"
        })
        self.assertEqual(status, 400)
        self.assertIn("language must be 'en' or 'ta'", data["error"])

    def test_bilingual_advisories_for_all_scenarios(self):
        """Verify both English and Tamil advisories function across all supported scenarios."""
        for scen in ["baseline", "heatwave", "extreme_heat"]:
            for lang in ["en", "ta"]:
                status, data = self._post_json("/api/agent/advisory", {
                    "scenario": scen,
                    "language": lang
                })
                self.assertEqual(status, 200)
                self.assertEqual(data["language"], lang)
                self.assertGreater(len(data["advisory"]), 20)


if __name__ == "__main__":
    unittest.main()
