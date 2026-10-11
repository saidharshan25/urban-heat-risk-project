
"""Local ClimateGuard AI agent API.

Uses only Python's standard library. Binds to loopback and does not send
external notifications. Forecast-derived information is kept separate from
illustrative scenario assumptions.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    PROJECT_ROOT / "data" / "processed" / "chennai"
    / "heat_hazard_forecast.json"
)
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
ALERT_LOG = OUTPUT_DIR / "agent_alert_log.jsonl"

HOST = "127.0.0.1"
PORT = 8081
MAX_BODY_BYTES = 16_384

SCENARIOS = {
    "baseline": {
        "label": "Baseline",
        "multiplier": 1.0,
    },
    "heatwave": {
        "label": "Heatwave",
        "multiplier": 1.10,
    },
    "extreme_heat": {
        "label": "Extreme heat",
        "multiplier": 1.20,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_report() -> dict:
    """Load and minimally validate the real forecast report."""
    if not REPORT_PATH.is_file():
        raise FileNotFoundError(
            f"Forecast report not found: {REPORT_PATH}"
        )

    with REPORT_PATH.open("r", encoding="utf-8") as file:
        report = json.load(file)

    required = {
        "metadata",
        "scientific_limitations_and_disclaimer",
        "hourly_forecast_hazard_records",
    }
    missing = required.difference(report)
    if missing:
        raise ValueError(
            "Forecast report is missing fields: "
            + ", ".join(sorted(missing))
        )

    if not isinstance(report["metadata"], dict):
        raise ValueError("Report metadata must be an object.")

    if not isinstance(report["hourly_forecast_hazard_records"], list):
        raise ValueError("Forecast records must be a list.")

    return report


def valid_records(report: dict) -> list[dict]:
    return [
        record
        for record in report["hourly_forecast_hazard_records"]
        if isinstance(record, dict)
        and record.get("valid") is True
        and isinstance(record.get("hazard_temperature_c"), (int, float))
    ]


class AgentAPIHandler(BaseHTTPRequestHandler):
    server_version = "ClimateGuardAgentAPI/1.0"

    def log_message(self, format_string, *args):
        # Keep concise local server logs.
        print(f"[agent-api] {self.address_string()} - {format_string % args}")

    def send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")

        origin = self.headers.get("Origin", "")
        if origin in (
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        origin = self.headers.get("Origin", "")
        if origin not in (
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ):
            self.send_json(403, {"error": "Origin not allowed."})
            return

        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def read_json_body(self) -> dict:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            raise ValueError("Content-Type must be application/json.")

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length.") from exc

        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("Request body must be between 1 and 16384 bytes.")

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must contain valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")

        return payload

    def do_GET(self):
        path = urlparse(self.path).path

        try:
            if path == "/api/agent/health":
                report_exists = REPORT_PATH.is_file()
                result = {
                    "status": "ok",
                    "service": "ClimateGuard AI Agent API",
                    "report_available": report_exists,
                    "report_path": str(REPORT_PATH),
                    "external_notifications_enabled": False,
                }
                if report_exists:
                    report = load_report()
                    result["valid_forecast_records"] = len(
                        valid_records(report)
                    )
                self.send_json(200, result)
                return

            if path == "/api/agent/outputs":
                files = []
                if OUTPUT_DIR.is_dir():
                    for item in sorted(OUTPUT_DIR.rglob("*")):
                        if (
                            item.is_file()
                            and item.suffix.lower() in {".json", ".jsonl", ".csv"}
                            and "agent_api.py" not in item.name
                        ):
                            try:
                                relative = item.relative_to(PROJECT_ROOT)
                            except ValueError:
                                continue
                            files.append({
                                "name": item.name,
                                "path": relative.as_posix(),
                                "size_bytes": item.stat().st_size,
                            })
                            if len(files) >= 100:
                                break

                self.send_json(200, {
                    "status": "ok",
                    "outputs": files,
                    "count": len(files),
                })
                return

            self.send_json(404, {"error": "Endpoint not found."})

        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json(500, {"error": str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path

        try:
            payload = self.read_json_body()
            scenario_name = payload.get("scenario", "baseline")

            if scenario_name not in SCENARIOS:
                self.send_json(400, {
                    "error": "Unknown scenario.",
                    "allowed_scenarios": list(SCENARIOS),
                })
                return

            scenario = SCENARIOS[scenario_name]

            if path == "/api/agent/scenario":
                count = payload.get("cooling_centres", 3)
                water_count = payload.get("water_points", 3)

                if (
                    isinstance(count, bool)
                    or not isinstance(count, int)
                    or count not in (3, 5)
                    or isinstance(water_count, bool)
                    or not isinstance(water_count, int)
                    or water_count not in (3, 5)
                ):
                    self.send_json(400, {
                        "error": "cooling_centres and water_points must be 3 or 5."
                    })
                    return

                report = load_report()
                records = valid_records(report)
                metadata = report["metadata"]

                # Use the highest recorded hazard in the real forecast.
                peak = max(
                    records,
                    key=lambda item: item["hazard_temperature_c"],
                    default=None,
                )

                self.send_json(200, {
                    "status": "ok",
                    "scenario": scenario["label"],
                    "scenario_key": scenario_name,
                    "scenario_multiplier": scenario["multiplier"],
                    "total_hexagons": None,
                    "underserved_hexagons": None,
                    "assumption": (
                        "Scenario multiplier is illustrative only. It is not "
                        "applied to the source forecast and is not a new prediction."
                    ),
                    "forecast_summary": {
                        "valid_records": len(records),
                        "alert_tier_distribution": metadata.get(
                            "alert_tier_distribution", {}
                        ),
                        "peak_observation": peak,
                    },
                    "cooling_centre_priorities": [],
                    "water_point_priorities": [],
                    "warnings": [
                        "No hexagon-level vulnerability dataset is connected; "
                        "hexagon counts are unknown.",
                        "No verified cooling-centre or water-point inventory is "
                        "connected; priority lists are intentionally empty.",
                        "This output is a preliminary planning aid, not an official warning.",
                    ],
                })
                return

            if path == "/api/agent/advisory":
                language = payload.get("language", "en").lower()
                if language not in ("en", "ta"):
                    self.send_json(400, {"error": "language must be 'en' or 'ta'."})
                    return

                report = load_report()
                records = valid_records(report)
                metadata = report["metadata"]

                tier_counts = metadata.get("alert_tier_distribution", {})
                peak = max(
                    records,
                    key=lambda item: item["hazard_temperature_c"],
                    default=None,
                )

                if language == "ta":
                    if peak:
                        advisory = (
                            f"ClimateGuard AI: {scenario['label']} சூழ்நிலைக்கான முன்னெச்சரிக்கை. "
                            "அதிக ஆபத்துள்ள பகுதிகளில் வசிப்பவர்கள் உள்ளூர் அதிகாரிகளின் "
                            "அறிவுறுத்தல்களைப் பின்பற்றவும். போதுமான அளவு தண்ணீர் குடிக்கவும், "
                            "கடுமையான வெயிலில் வெளியில் இருப்பதைத் தவிர்க்கவும். "
                            "உடல்நலக் குறைவு ஏற்பட்டால் மருத்துவ உதவியை நாடவும். "
                            "இந்த அறிக்கை ஆரம்பகட்ட மாதிரி தரவு அடிப்படையிலானது; அதிகாரப்பூர்வ "
                            "எச்சரிக்கைக்கு மாற்றாகாது."
                        )
                    else:
                        advisory = (
                            "செல்லுபடியாகும் வெப்பநிலை பதிவுகள் எதுவும் கிடைக்கவில்லை. "
                            "மூலத் தரவைச் சரிபார்த்து, அதிகாரப்பூர்வ உள்ளூர் வழிகாட்டுதலைப் பெறவும்."
                        )
                    disclaimer = (
                        "இது ஆரம்பகட்ட தகவல் ஆலோசனை மட்டுமே, அதிகாரப்பூர்வ வானிலை எச்சரிக்கை அல்லது மருத்துவ ஆலோசனை அல்ல."
                    )
                else:
                    if peak:
                        advisory = (
                            f"ClimateGuard AI precautionary advisory: {scenario['label']} scenario. "
                            "Review the forecast peak and follow local public-health "
                            "guidance. Consider routine heat-safety measures, drinking "
                            "water, and checking on people who may be more vulnerable. "
                            "Confirm conditions with authoritative local sources."
                        )
                    else:
                        advisory = (
                            "No valid hazard-temperature records are available. "
                            "Check the source data and consult authoritative local guidance."
                        )
                    disclaimer = (
                        "This is a preliminary informational advisory, not an "
                        "official weather alert or medical advice."
                    )

                self.send_json(200, {
                    "status": "ok",
                    "scenario": scenario["label"],
                    "language": language,
                    "advisory": advisory,
                    "forecast_records": len(records),
                    "alert_tier_distribution": tier_counts,
                    "peak_observation": peak,
                    "official_warning": False,
                    "disclaimer": disclaimer,
                })
                return

            if path == "/api/agent/alert":
                audience = payload.get("audience", "response_team")
                if audience != "response_team":
                    self.send_json(400, {
                        "error": "Only the local response_team simulation is supported."
                    })
                    return

                event = {
                    "timestamp_utc": utc_now(),
                    "scenario": scenario_name,
                    "audience": audience,
                    "status": "simulated_logged_locally",
                    "external_notification_sent": False,
                    "message": (
                        "Simulation only. No email, SMS, or external notification was sent."
                    ),
                }

                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                with ALERT_LOG.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(event, ensure_ascii=False) + "\n")

                self.send_json(200, {
                    "status": "simulated",
                    "external_notification_sent": False,
                    "log_file": ALERT_LOG.relative_to(PROJECT_ROOT).as_posix(),
                    "message": event["message"],
                })
                return

            self.send_json(404, {"error": "Endpoint not found."})

        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except (OSError, json.JSONDecodeError) as exc:
            self.send_json(500, {"error": str(exc)})


def main():
    try:
        report = load_report()
        print(f"Forecast report loaded: {len(valid_records(report))} valid records")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Warning: forecast report is not ready: {exc}")

    server = ThreadingHTTPServer((HOST, PORT), AgentAPIHandler)
    print(f"ClimateGuard AI Agent API listening at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop. External notifications are disabled.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Agent API...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
