"""Critical infrastructure and cooling facilities ingestor for Chennai."""

import json
import time
import csv
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from shapely.geometry import Point

from src.ingestion.config import (
    CACHE_DIR,
    FACILITY_CATEGORIES,
    OVERPASS_ENDPOINTS,
    USER_AGENT,
    CHENNAI_BBOX,
    FACILITY_CACHE_TTL_SECONDS,
    VERIFIED_FACILITIES_CSV_PATH,
)


class FacilitiesIngestor:
    """Ingests, caches, and validates critical infrastructure and heat relief assets.
    
    Includes hospitals, schools, parks, community halls, and drinking water sources.
    Idempotent, preserves last known valid cache on network failure, and supports
    local verified ground truth CSV fallback without unauthorized external calls.
    """

    def __init__(self,
                 cache_dir: Optional[Path] = None,
                 facilities_csv_path: Optional[Path] = None):
        self.cache_dir = Path(cache_dir or CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "chennai_facilities_cache.json"
        self.facilities_csv_path = Path(facilities_csv_path or VERIFIED_FACILITIES_CSV_PATH)

    def has_cached_data(self) -> bool:
        """Check if cached facilities file exists."""
        return self.cache_file.is_file()

    def load_cached_facilities(self) -> Optional[Dict[str, Any]]:
        """Load facilities from local cache if present and valid JSON."""
        if not self.has_cached_data():
            return None
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "counts" in data and isinstance(data["counts"], dict):
                return data
            return None
        except Exception:
            return None

    def is_cache_stale(self, max_age_seconds: int = FACILITY_CACHE_TTL_SECONDS) -> bool:
        """Check whether local cache is older than the configured TTL."""
        data = self.load_cached_facilities()
        if not data:
            return True
        cached_time = data.get("cached_timestamp", 0)
        return (time.time() - cached_time) > max_age_seconds

    def load_counts_from_local_csv(self) -> Optional[Dict[str, int]]:
        """Extract verified facility counts from local processed OSM dataset.
        
        Reads genuine Chennai facilities CSV without making any external network requests.
        """
        if not self.facilities_csv_path.is_file():
            return None

        type_mapping = {
            "hospital": "hospitals",
            "school": "schools",
            "community_centre": "community_centres",
            "library": "libraries",
            "park": "parks",
            "water": "drinking_water",
            "drinking_water": "drinking_water",
        }

        counts: Dict[str, int] = {
            "hospitals": 0,
            "schools": 0,
            "community_centres": 0,
            "libraries": 0,
            "parks": 0,
            "drinking_water": 0,
        }

        try:
            with open(self.facilities_csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # If in_city flag exists, ensure only in-city facilities are counted
                    in_city_val = row.get("in_city")
                    if in_city_val is not None and str(in_city_val).strip().lower() == "false":
                        continue
                    raw_type = str(row.get("type", "")).strip().lower()
                    target_cat = type_mapping.get(raw_type)
                    if target_cat and target_cat in counts:
                        counts[target_cat] += 1
            return counts
        except Exception:
            return None

    def _save_cache(self, counts: Dict[str, int], source: str = "overpass_api") -> None:
        """Persist verified category counts to local cache file."""
        cache_payload = {
            "city": "Chennai, Tamil Nadu, India",
            "counts": counts,
            "cached_timestamp": time.time(),
            "source": source,
        }
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_payload, f, indent=2)

    def query_overpass_counts(self,
                              poly_coords_str: Optional[str] = None,
                              timeout_sec: int = 35) -> Dict[str, Optional[int]]:
        """Query Overpass API for counts in each facility category with mirror fallbacks.
        
        CRITICAL: Distinguishes confirmed 0 responses from network/endpoint failures.
        Returns None for a category if all mirror endpoints failed or timed out.
        Returns an integer (>= 0) only if an endpoint returned a confirmed response.
        """
        if not poly_coords_str:
            w, s, e, n = (
                CHENNAI_BBOX["west"],
                CHENNAI_BBOX["south"],
                CHENNAI_BBOX["east"],
                CHENNAI_BBOX["north"],
            )
            area_filter = f"({s},{w},{n},{e})"
        else:
            area_filter = f'(poly:"{poly_coords_str}")'

        queries = {
            "hospitals": f"""[out:json][timeout:{timeout_sec}];(nwr["amenity"="hospital"]{area_filter};);out count;""",
            "schools": f"""[out:json][timeout:{timeout_sec}];(nwr["amenity"="school"]{area_filter};);out count;""",
            "community_centres": f"""[out:json][timeout:{timeout_sec}];(nwr["amenity"="community_centre"]{area_filter};);out count;""",
            "libraries": f"""[out:json][timeout:{timeout_sec}];(nwr["amenity"="library"]{area_filter};);out count;""",
            "parks": f"""[out:json][timeout:{timeout_sec}];(nwr["leisure"="park"]{area_filter};);out count;""",
            "drinking_water": f"""[out:json][timeout:{timeout_sec}];(nwr["amenity"="drinking_water"]{area_filter};);out count;""",
        }

        results: Dict[str, Optional[int]] = {}
        headers = {"User-Agent": USER_AGENT}

        for category, q in queries.items():
            category_count: Optional[int] = None
            category_succeeded = False

            for endpoint in OVERPASS_ENDPOINTS:
                try:
                    resp = requests.post(
                        endpoint,
                        data={"data": q},
                        headers=headers,
                        timeout=timeout_sec + 10
                    )
                    if resp.status_code == 200:
                        elems = resp.json().get("elements", [])
                        if elems and "tags" in elems[0]:
                            category_count = int(elems[0]["tags"].get("total", 0))
                        else:
                            category_count = 0
                        category_succeeded = True
                        break
                except Exception:
                    continue

            results[category] = category_count if category_succeeded else None
            time.sleep(0.5)

        return results

    def ingest_and_validate(self,
                            boundary_polygon: Optional[Any] = None,
                            force_refresh: bool = False) -> Dict[str, Any]:
        """Ingest facilities, prioritizing local cache, and return validation report.
        
        Preserves existing valid cache when refresh fails.
        Falls back to local verified CSV if cache is unavailable or corrupted.
        """
        cached_data = self.load_cached_facilities()
        counts: Dict[str, int] = {}
        from_cache = False
        warnings: List[str] = []

        if not force_refresh and cached_data:
            cached_counts = cached_data.get("counts", {})
            # Verify cached data is not corrupted by previous zero-school defect
            if cached_counts.get("schools", 0) > 0 or cached_counts.get("hospitals", 0) > 0:
                counts = cached_counts
                from_cache = True
            else:
                # Cache was corrupted by previous failed query; recover from verified CSV
                csv_counts = self.load_counts_from_local_csv()
                if csv_counts:
                    counts = csv_counts
                    self._save_cache(counts, source="local_verified_csv_recovery")
                    from_cache = True
                    warnings.append("Recovered corrupted cache from verified local facilities dataset.")

        if not counts:
            # Query Overpass API
            poly_str = None
            if boundary_polygon and hasattr(boundary_polygon, "simplify"):
                simplified = boundary_polygon.simplify(0.005)
                if simplified.geom_type == "MultiPolygon":
                    simplified = max(simplified.geoms, key=lambda a: a.area)
                coords = list(simplified.exterior.coords)
                poly_str = " ".join(f"{lat:.5f} {lon:.5f}" for lon, lat in coords)

            new_results = self.query_overpass_counts(poly_coords_str=poly_str)
            failed_cats = [k for k, v in new_results.items() if v is None]

            if failed_cats:
                # Network or endpoint failure occurred
                warnings.append(f"Overpass query failed for categories: {failed_cats}")
                if cached_data and "counts" in cached_data and cached_data["counts"].get("hospitals", 0) > 0:
                    # PRESERVE existing valid cache
                    counts = dict(cached_data["counts"])
                    from_cache = True
                    warnings.append("Preserved existing valid cache after failed Overpass refresh.")
                else:
                    # Fall back to verified local CSV
                    csv_counts = self.load_counts_from_local_csv()
                    if csv_counts:
                        counts = csv_counts
                        self._save_cache(counts, source="local_verified_csv_fallback")
                        from_cache = False
                        warnings.append("Loaded verified counts from local facilities dataset.")
                    else:
                        # No cache and no local CSV available; fill failed categories with 0
                        counts = {k: (v if v is not None else 0) for k, v in new_results.items()}
                        from_cache = False
            else:
                # All categories succeeded
                counts = {k: int(v) for k, v in new_results.items() if v is not None}
                from_cache = False
                self._save_cache(counts, source="overpass_api")

        # Validation checks
        total_assets = sum(counts.values())
        hospitals_pass = counts.get("hospitals", 0) >= 5
        schools_pass = counts.get("schools", 0) >= 20
        has_essential_assets = (hospitals_pass and schools_pass)
        status = "PASS" if (total_assets > 0 and has_essential_assets) else "WARN"

        report = {
            "status": status,
            "from_cache": from_cache,
            "cache_file": str(self.cache_file),
            "total_assets_found": total_assets,
            "category_counts": counts,
            "hospitals_pass": hospitals_pass,
            "schools_pass": schools_pass,
            "cooling_relief_assets": {
                "parks": counts.get("parks", 0),
                "drinking_water": counts.get("drinking_water", 0),
                "community_centres": counts.get("community_centres", 0),
            },
            "warnings": warnings,
        }

        return {
            "status": status,
            "counts": counts,
            "report": report,
        }
