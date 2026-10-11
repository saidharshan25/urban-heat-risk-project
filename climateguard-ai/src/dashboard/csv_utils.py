"""CSV export, parsing, and integrity validation utilities for ClimateGuard AI."""

import csv
import io
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


def export_records_to_csv(records: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> str:
    """Export a list of dictionary records to an RFC 4180 compliant CSV string.
    
    Properly escapes quotes, commas, and newlines. Handles empty datasets gracefully.
    """
    if not records and not fieldnames:
        return ""

    if not fieldnames and records:
        # Preserve first record keys order
        fieldnames = list(records[0].keys())

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames or [],
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\r\n",
    )
    writer.writeheader()
    for row in records:
        # Clean row to match fieldnames, converting None to empty string
        cleaned_row = {k: ("" if row.get(k) is None else row.get(k)) for k in (fieldnames or [])}
        writer.writerow(cleaned_row)

    return output.getvalue()


def parse_csv_string(csv_text: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Parse CSV text strictly following RFC 4180 conventions.
    
    Returns (headers, records). Does not confuse apostrophes with quotes.
    Handles empty text gracefully.
    """
    if not csv_text or not csv_text.strip():
        return [], []

    stream = io.StringIO(csv_text.strip())
    reader = csv.reader(stream)
    try:
        headers = next(reader)
    except StopIteration:
        return [], []

    headers = [h.strip() for h in headers]
    records: List[Dict[str, str]] = []

    for row in reader:
        if not row:
            continue
        record = {}
        for idx, h in enumerate(headers):
            val = row[idx] if idx < len(row) else ""
            record[h] = val
        records.append(record)

    return headers, records


def validate_csv_file(
    file_path: Path,
    expected_headers: Optional[List[str]] = None,
    min_rows: int = 1,
) -> Dict[str, Any]:
    """Validate a CSV file on disk for header integrity, row counts, and data consistency.
    
    Returns structured report with status, headers, row_count, errors, and warnings.
    """
    path = Path(file_path)
    report: Dict[str, Any] = {
        "file_path": str(path),
        "exists": path.is_file(),
        "status": "FAIL",
        "headers": [],
        "row_count": 0,
        "errors": [],
        "warnings": [],
    }

    if not report["exists"]:
        report["errors"].append(f"File not found: {path}")
        return report

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError as exc:
        report["errors"].append(f"Encoding error: {exc}")
        return report

    headers, records = parse_csv_string(content)
    report["headers"] = headers
    report["row_count"] = len(records)

    if not headers:
        report["errors"].append("CSV has no headers or is empty.")
        return report

    if expected_headers:
        missing = [h for h in expected_headers if h not in headers]
        if missing:
            report["errors"].append(f"Missing expected headers: {missing}")

    if len(records) < min_rows:
        report["errors"].append(f"Row count {len(records)} is below required minimum {min_rows}.")

    # Check for empty critical identifiers or malformed rows
    for idx, row in enumerate(records[:100]):  # Sample first 100
        for h, v in row.items():
            if h in ("h3_id", "rank", "facility_id") and not str(v).strip():
                report["warnings"].append(f"Row {idx + 1} has empty identifier for '{h}'.")

    if not report["errors"]:
        report["status"] = "PASS"

    return report
