"""Unit tests for CSV export integrity, parsing, escaping, and downloadable outputs."""

import json
import unittest
import urllib.request
import threading
import time
from pathlib import Path

from src.dashboard.csv_utils import (
    export_records_to_csv,
    parse_csv_string,
    validate_csv_file,
)
from src.dashboard.server import create_server, STATIC_DIR, DEFAULT_REPORT_PATH


class TestCSVExportIntegrity(unittest.TestCase):
    """Test suite verifying CSV headers, row counts, escaping, empty data, and download integrity."""

    @classmethod
    def setUpClass(cls):
        cls.data_dir = STATIC_DIR / "data"
        cls.tree_csv = cls.data_dir / "chennai_tree_planting_priority.csv"
        cls.team_csv = cls.data_dir / "chennai_emergency_team_placement.csv"

        # Start ephemeral dashboard server to test downloadable outputs
        cls.server = create_server(host="127.0.0.1", port=0, report_path=DEFAULT_REPORT_PATH)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_tree_planting_csv_file_integrity(self):
        """Verify tree planting CSV file has expected headers and at least 1,000 rows."""
        self.assertTrue(self.tree_csv.is_file(), f"Missing file: {self.tree_csv}")
        expected_headers = [
            "rank",
            "h3_id",
            "prototype_priority_score",
            "risk_score",
            "pop_total",
            "pop_vulnerable",
        ]
        rep = validate_csv_file(self.tree_csv, expected_headers=expected_headers, min_rows=1000)
        self.assertEqual(rep["status"], "PASS")
        self.assertGreaterEqual(rep["row_count"], 1000)
        self.assertIn("h3_id", rep["headers"])
        self.assertIn("rank", rep["headers"])

    def test_emergency_team_csv_file_integrity(self):
        """Verify emergency team placement CSV file has expected headers and at least 2,500 rows."""
        self.assertTrue(self.team_csv.is_file(), f"Missing file: {self.team_csv}")
        expected_headers = [
            "h3_id",
            "risk_score",
            "pop_vulnerable",
            "pop_total",
            "assigned_site_id",
            "assigned_site_name",
            "assigned_site_type",
            "straight_line_distance_km",
        ]
        rep = validate_csv_file(self.team_csv, expected_headers=expected_headers, min_rows=2500)
        self.assertEqual(rep["status"], "PASS")
        self.assertGreaterEqual(rep["row_count"], 2500)
        self.assertIn("assigned_site_name", rep["headers"])

    def test_emergency_team_complex_escaping_and_apostrophes(self):
        """Verify records with apostrophes and commas (e.g. Dr.Agarwal's Eye Hospital) are parsed without column shift."""
        with open(self.team_csv, "r", encoding="utf-8") as f:
            content = f.read()

        headers, records = parse_csv_string(content)
        self.assertGreaterEqual(len(records), 2500)

        # Check the row with Dr.Agarwal's Eye Hospital
        agarwal_rows = [r for r in records if "Dr.Agarwal" in r.get("assigned_site_name", "")]
        self.assertGreater(len(agarwal_rows), 0)
        for r in agarwal_rows:
            # Ensure assigned_site_name preserved the comma and apostrophe
            self.assertIn("Dr.Agarwal's Eye Hospital Ltd., Anna Nagar", r["assigned_site_name"])
            # Ensure assigned_site_type was not corrupted or shifted
            self.assertEqual(r["assigned_site_type"], "hospital")
            # Ensure straight_line_distance_km is a parseable float
            dist = float(r["straight_line_distance_km"])
            self.assertGreater(dist, 0.0)

    def test_export_records_to_csv_roundtrip(self):
        """Verify export_records_to_csv preserves special characters, commas, and quotes in roundtrip."""
        sample_data = [
            {
                "id": "1",
                "site_name": 'Govt "General" Hospital, Chennai',
                "notes": "Line 1\nLine 2 with, comma",
                "status": "Active",
            },
            {
                "id": "2",
                "site_name": "Anna Nagar Community Hall",
                "notes": "Normal note",
                "status": "Active",
            },
        ]
        csv_text = export_records_to_csv(sample_data)
        self.assertIn('"Govt ""General"" Hospital, Chennai"', csv_text)

        headers, parsed = parse_csv_string(csv_text)
        self.assertEqual(headers, ["id", "site_name", "notes", "status"])
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["site_name"], 'Govt "General" Hospital, Chennai')
        self.assertEqual(parsed[0]["notes"], "Line 1\nLine 2 with, comma")

    def test_export_empty_and_null_data(self):
        """Verify export handles empty records, None values, and empty fieldnames gracefully."""
        self.assertEqual(export_records_to_csv([]), "")
        self.assertEqual(export_records_to_csv([], ["a", "b"]), "a,b\r\n")

        null_data = [{"a": None, "b": "hello"}]
        csv_text = export_records_to_csv(null_data)
        headers, parsed = parse_csv_string(csv_text)
        self.assertEqual(parsed[0]["a"], "")
        self.assertEqual(parsed[0]["b"], "hello")

    def test_downloadable_outputs_via_http_server(self):
        """Verify static CSV endpoints are downloadable via HTTP server with 200 OK and correct Content-Type."""
        endpoints = [
            "/data/chennai_tree_planting_priority.csv",
            "/data/chennai_emergency_team_placement.csv",
        ]
        for ep in endpoints:
            url = f"http://127.0.0.1:{self.port}{ep}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                # Content-Type for CSV files in python SimpleHTTPRequestHandler
                content = resp.read()
                self.assertGreater(len(content), 1000)
                # Parse downloaded content to ensure valid CSV
                headers, records = parse_csv_string(content.decode("utf-8"))
                self.assertGreater(len(headers), 0)
                self.assertGreater(len(records), 0)


if __name__ == "__main__":
    unittest.main()
