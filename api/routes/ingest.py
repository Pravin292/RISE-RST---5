import io
import uuid
import time
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse

from services.kafka_producer import kafka_service
from services.neo4j_service import neo4j_service

logger = logging.getLogger("ingest_router")
router = APIRouter()

@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_csv(file: UploadFile = File(...)):
    # 1. File existence validation
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided in the upload request."
        )

    # 2. Extension validation
    filename = file.filename
    if not filename.lower().endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Please upload a valid .csv file."
        )

    # 3. Read content
    try:
        content = await file.read()
        if not content or len(content.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded CSV file is empty (0 bytes)."
            )

        # Parse CSV with pandas for validation and preview
        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse CSV file: {str(e)}"
            )

        if df.empty and len(df.columns) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The CSV contains no headers or readable columns."
            )

        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The CSV file contains headers but zero data rows."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error processing upload: {str(e)}"
        )

    # 4. Generate Job & Dataset Metadata
    job_id = str(uuid.uuid4())[:8]
    dataset_id = f"dataset_{job_id}"
    uploaded_at = datetime.utcnow().isoformat()
    rows_received = len(df)
    columns_list = list(df.columns)

    # 5. Calculate WOW Feature 1: Data Health Score
    missing_cells = int(df.isna().sum().sum())
    total_cells = rows_received * len(columns_list)
    missing_pct = (missing_cells / total_cells * 100) if total_cells > 0 else 0
    
    duplicate_rows = int(df.duplicated().sum())
    duplicate_pct = (duplicate_rows / rows_received * 100) if rows_received > 0 else 0

    # Score calculation out of 100
    raw_score = 100 - (missing_pct * 0.4) - (duplicate_pct * 0.6)
    health_score = max(0, min(100, int(round(raw_score))))

    health_metrics = {
        "health_score": health_score,
        "total_rows": rows_received,
        "columns_count": len(columns_list),
        "columns": columns_list,
        "missing_cells": missing_cells,
        "duplicate_rows": duplicate_rows
    }

    # 6. Initialize Job in Neo4j
    neo4j_service.create_job(job_id=job_id, filename=filename, rows_total=rows_received)

    # 7. Publish row-by-row to Kafka
    rows_sent = 0
    for idx, row in df.iterrows():
        row_dict = {}
        for col in columns_list:
            val = row[col]
            if pd.isna(val):
                row_dict[str(col)] = None
            elif isinstance(val, (int, float)):
                row_dict[str(col)] = val
            else:
                row_dict[str(col)] = str(val)

        row_index = idx + 1
        success = kafka_service.send_row_message(
            dataset_id=dataset_id,
            filename=filename,
            row_index=row_index,
            row_data=row_dict,
            uploaded_at=uploaded_at
        )
        if success:
            rows_sent += 1

    kafka_service.flush()
    logger.info(f"Job {job_id}: Successfully sent {rows_sent}/{rows_received} rows to Kafka.")

    # 8. Return 202 Accepted Response
    preview_data = df.head(5).fillna("").to_dict(orient="records")

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": job_id,
            "dataset_id": dataset_id,
            "filename": filename,
            "rows_received": rows_received,
            "status": "queued",
            "preview": preview_data,
            "health_metrics": health_metrics
        }
    )
