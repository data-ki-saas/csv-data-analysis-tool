import uuid
from pathlib import Path

import aiofiles
import duckdb
from fastapi import HTTPException, UploadFile

from src.core.auth import CurrentUser
from src.core.config import settings
from src.datasets import repository
from src.datasets.duckdb_manager import duckdb_manager
from src.datasets.schemas import ColumnInfo, DatasetInfo, DatasetPreview, UploadResponse
from src.storage import r2_client

_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB


async def _stream_upload_to_disk(file: UploadFile, destination: Path) -> None:
    written = 0
    async with aiofiles.open(destination, "wb") as out:
        while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
            written += len(chunk)
            if written > settings.max_upload_size_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds the {settings.max_upload_size_mb} MB upload limit",
                )
            await out.write(chunk)
    if written == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")


async def ingest_csv_upload(file: UploadFile, user: CurrentUser) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    dataset_id = uuid.uuid4().hex
    tmp_csv_path = settings.scratch_dir / f"{dataset_id}.upload.csv"
    raw_key = f"raw/{dataset_id}.csv"
    parquet_key = f"processed/{dataset_id}.parquet"

    try:
        await _stream_upload_to_disk(file, tmp_csv_path)
        result = duckdb_manager.ingest_and_export(tmp_csv_path, parquet_key)
        r2_client.upload_raw_file(tmp_csv_path, raw_key)
    except duckdb.Error as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}") from exc
    finally:
        tmp_csv_path.unlink(missing_ok=True)

    schema_dicts = [{"name": col.name, "type": col.type} for col in result.schema]
    record = repository.create_dataset(
        owner_id=user.id,
        filename=file.filename,
        row_count=result.row_count,
        schema=schema_dicts,
        raw_key=raw_key,
        parquet_key=parquet_key,
    )

    return UploadResponse(
        dataset_id=record.id,
        filename=record.filename,
        row_count=record.row_count,
        schema=[ColumnInfo(**col) for col in record.schema],
        preview=DatasetPreview(columns=result.preview.columns, rows=result.preview.rows),
    )


def get_dataset_info(dataset_id: str, user: CurrentUser) -> DatasetInfo:
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return DatasetInfo(
        dataset_id=record.id,
        filename=record.filename,
        row_count=record.row_count,
        schema=[ColumnInfo(**col) for col in record.schema],
    )


def list_datasets(user: CurrentUser) -> list[DatasetInfo]:
    return [
        DatasetInfo(
            dataset_id=record.id,
            filename=record.filename,
            row_count=record.row_count,
            schema=[ColumnInfo(**col) for col in record.schema],
        )
        for record in repository.list_datasets(user.id)
    ]


def delete_dataset(dataset_id: str, user: CurrentUser) -> None:
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    r2_client.delete_object(record.raw_key)
    r2_client.delete_object(record.parquet_key)
    repository.delete_dataset(dataset_id, user.id)
