import duckdb
from fastapi import APIRouter, Depends, HTTPException

from src.core.auth import CurrentUser, get_current_user
from src.datasets import repository
from src.datasets.duckdb_manager import UnsafeQueryError, duckdb_manager
from src.query.schemas import QueryRequest, QueryResponse

router = APIRouter(prefix="/api/datasets", tags=["query"])


@router.post("/{dataset_id}/query", response_model=QueryResponse)
async def query_dataset(
    dataset_id: str, request: QueryRequest, user: CurrentUser = Depends(get_current_user)
) -> QueryResponse:
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        result = await duckdb_manager.execute_query(
            record.parquet_key,
            request.sql,
            request.max_rows,
            value_remaps=record.value_remaps,
            value_replacements=record.value_replacements,
        )
    except UnsafeQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except duckdb.Error as exc:
        raise HTTPException(status_code=400, detail=f"Query failed: {exc}") from exc

    return QueryResponse(
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
    )
