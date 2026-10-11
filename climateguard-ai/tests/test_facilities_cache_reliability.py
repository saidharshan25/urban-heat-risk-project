"""Unit tests for facilities cache reliability, failure preservation, and local fallback."""

import json
import time
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock
import requests

from src.ingestion.facilities_ingestor import FacilitiesIngestor


class TestFacilitiesCacheReliability(unittest.TestCase):
    """Test suite ensuring facilities cache resilience under network anomalies and edge cases."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.cache_dir = self.temp_path / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "chennai_facilities_cache.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_failed_refresh_preserves_existing_valid_cache(self):
        """Verify that a network timeout or API failure during refresh preserves the existing valid cache."""
        valid_cache = {
            "city": "Chennai, Tamil Nadu, India",
            "counts": {
                "hospitals": 55,
                "schools": 120,
                "community_centres": 25,
                "libraries": 30,
                "parks": 45,
                "drinking_water": 12,
            },
            "cached_timestamp": time.time() - 3600,
            "source": "initial_valid_seed",
        }
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(valid_cache, f)

        ingestor = FacilitiesIngestor(cache_dir=self.cache_dir)

        # Mock network failure across all Overpass endpoints
        with patch("requests.post", side_effect=requests.exceptions.ConnectTimeout("Connection timed out")):
            res = ingestor.ingest_and_validate(force_refresh=True)

        # The existing valid cache must be preserved
        self.assertEqual(res["status"], "PASS")
        self.assertTrue(res["report"]["from_cache"])
        self.assertEqual(res["counts"]["schools"], 120)
        self.assertEqual(res["counts"]["hospitals"], 55)

        # Cache file on disk must NOT be overwritten with zeroes
        with open(self.cache_file, "r", encoding="utf-8") as f:
            persisted = json.load(f)
        self.assertEqual(persisted["counts"]["schools"], 120)
        self.assertEqual(persisted["counts"]["hospitals"], 55)

    def test_distinguish_confirmed_zero_from_network_failure(self):
        """Verify that a confirmed 0 result from API is distinguished from a network exception."""
        ingestor = FacilitiesIngestor(cache_dir=self.cache_dir)

        def mock_overpass_post(endpoint, data=None, headers=None, timeout=None):
            query = data.get("data", "")
            if '["amenity"="drinking_water"]' in query:
                # API explicitly responds with count 0
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "elements": [{"type": "count", "tags": {"total": "0"}}]
                }
                return mock_resp
            elif '["amenity"="school"]' in query:
                # Network exception / timeout
                raise requests.exceptions.ReadTimeout("Overpass timeout")
            else:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "elements": [{"type": "count", "tags": {"total": "42"}}]
                }
                return mock_resp

        with patch("requests.post", side_effect=mock_overpass_post):
            results = ingestor.query_overpass_counts()

        # Confirmed 0 from API must be 0
        self.assertEqual(results["drinking_water"], 0)
        # Network failure must be None (NOT 0)
        self.assertIsNone(results["schools"])
        # Successful response must be integer
        self.assertEqual(results["hospitals"], 42)

    def test_successful_refresh_updates_cache(self):
        """Verify that a successful refresh properly updates cache and returns new counts."""
        old_cache = {
            "city": "Chennai, Tamil Nadu, India",
            "counts": {"hospitals": 10, "schools": 25, "community_centres": 5, "libraries": 5, "parks": 5, "drinking_water": 5},
            "cached_timestamp": time.time() - 86400,
        }
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(old_cache, f)

        ingestor = FacilitiesIngestor(cache_dir=self.cache_dir)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "elements": [{"type": "count", "tags": {"total": "88"}}]
        }

        with patch("requests.post", return_value=mock_resp):
            res = ingestor.ingest_and_validate(force_refresh=True)

        self.assertEqual(res["status"], "PASS")
        self.assertFalse(res["report"]["from_cache"])
        self.assertEqual(res["counts"]["schools"], 88)
        self.assertEqual(res["counts"]["hospitals"], 88)

        # File on disk must reflect updated count
        with open(self.cache_file, "r", encoding="utf-8") as f:
            persisted = json.load(f)
        self.assertEqual(persisted["counts"]["schools"], 88)

    def test_stale_cache_detection(self):
        """Verify stale cache detection based on timestamp TTL."""
        ingestor = FacilitiesIngestor(cache_dir=self.cache_dir)

        # No file -> stale
        self.assertTrue(ingestor.is_cache_stale())

        # Old file -> stale
        old_time = time.time() - 100000
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump({"counts": {"hospitals": 10}, "cached_timestamp": old_time}, f)
        self.assertTrue(ingestor.is_cache_stale(max_age_seconds=86400))

        # Fresh file -> not stale
        fresh_time = time.time() - 3600
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump({"counts": {"hospitals": 10}, "cached_timestamp": fresh_time}, f)
        self.assertFalse(ingestor.is_cache_stale(max_age_seconds=86400))

    def test_local_csv_fallback_when_cache_missing_and_network_fails(self):
        """Verify that when no cache exists and Overpass fails, local verified CSV is loaded safely."""
        dummy_csv = self.temp_path / "dummy_facilities.csv"
        with open(dummy_csv, "w", encoding="utf-8") as f:
            f.write("facility_id,type,name,lat,lon,in_city\n")
            for i in range(12):
                f.write(f"node/{i},hospital,Hospital {i},13.0,80.2,True\n")
            for i in range(25):
                f.write(f"node/{100+i},school,School {i},13.0,80.2,True\n")
            for i in range(8):
                f.write(f"node/{200+i},park,Park {i},13.0,80.2,True\n")

        ingestor = FacilitiesIngestor(cache_dir=self.cache_dir, facilities_csv_path=dummy_csv)

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Offline")):
            res = ingestor.ingest_and_validate(force_refresh=True)

        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["counts"]["hospitals"], 12)
        self.assertEqual(res["counts"]["schools"], 25)
        self.assertEqual(res["counts"]["parks"], 8)
        self.assertTrue(self.cache_file.is_file())


if __name__ == "__main__":
    unittest.main()
