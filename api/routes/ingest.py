import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, status

from models.schemas import IngestResponse
from services.csv_utils import CSVValidationError, parse_csv
from services.kafka_producer import producer_service
from services.neo4j_service import neo4j_service

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_csv(file: UploadFile):
    raw_bytes = await file.read()

    try:
        columns, rows = parse_csv(raw_bytes, file.filename or "")
    except CSVValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Deterministic id (filename + content hash) so re-uploading the exact same
    # CSV maps to the same dataset_id/row_key, and Loader's MERGE is a true no-op
    # instead of creating a second logical dataset.
    fingerprint = (file.filename or "").encode() + b"|" + raw_bytes
    dataset_id = hashlib.sha256(fingerprint).hexdigest()[:16]
    uploaded_at = datetime.now(timezone.utc).isoformat()
    total_rows = len(rows)

    neo4j_service.create_dataset(dataset_id, file.filename, uploaded_at, total_rows, columns)

    for idx, row in enumerate(rows, start=1):
        message = {
            "dataset_id": dataset_id,
            "filename": file.filename,
            "uploaded_at": uploaded_at,
            "total_rows": total_rows,
            "columns": columns,
            "row_index": idx,
            "row": row,
        }
        producer_service.publish_row(message)

    producer_service.flush()

    return IngestResponse(job_id=dataset_id, rows_received=total_rows, status="queued")
