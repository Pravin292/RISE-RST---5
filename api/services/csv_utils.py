import csv
import io
import re


class CSVValidationError(Exception):
    """Raised when an uploaded file fails CSV validation."""


def normalize_column(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = name.strip("_")
    return name or "column"


def parse_csv(raw_bytes: bytes, filename: str) -> tuple[list[str], list[dict[str, str]]]:
    """Validate and parse CSV bytes into (normalized_headers, rows).

    Raises CSVValidationError with a human-readable message on any
    validation failure (wrong extension, empty file, header-only file).
    """
    if not filename.lower().endswith(".csv"):
        raise CSVValidationError("Please upload a valid CSV file.")

    if not raw_bytes or not raw_bytes.strip():
        raise CSVValidationError("The uploaded CSV contains no data.")

    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CSVValidationError("Please upload a valid CSV file.")

    if not text.strip():
        raise CSVValidationError("The uploaded CSV contains no data.")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    rows = [r for r in rows if any(cell.strip() for cell in r)]

    if not rows:
        raise CSVValidationError("The uploaded CSV contains no data.")

    raw_headers = rows[0]
    if not any(h.strip() for h in raw_headers):
        raise CSVValidationError("Please upload a valid CSV file.")

    data_rows = rows[1:]
    if not data_rows:
        raise CSVValidationError("The CSV contains headers but no data rows.")

    headers = [normalize_column(h) for h in raw_headers]
    # de-duplicate normalized headers
    seen: dict[str, int] = {}
    final_headers = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            final_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            final_headers.append(h)

    parsed_rows = []
    for row in data_rows:
        record = {}
        for idx, header in enumerate(final_headers):
            record[header] = row[idx].strip() if idx < len(row) else ""
        parsed_rows.append(record)

    return final_headers, parsed_rows
