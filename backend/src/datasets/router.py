from fastapi import APIRouter, Depends, UploadFile

from src.core.auth import CurrentUser, get_current_user
from src.datasets import service
from src.datasets.schemas import (
    DatasetInfo,
    DatasetSchemaResponse,
    GenerateInsightsRequest,
    InsightsResponse,
    ReportStrategyRequest,
    ReportStrategyResponse,
    ReviewColumnsRequest,
    UpdateColumnRequest,
    UpdateDatasetRequest,
    UploadResponse,
)

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.post("/upload", response_model=UploadResponse, response_model_by_alias=True)
async def upload_dataset(
    file: UploadFile, user: CurrentUser = Depends(get_current_user)
) -> UploadResponse:
    return await service.ingest_csv_upload(file, user)


@router.get("", response_model=list[DatasetInfo], response_model_by_alias=True)
async def list_datasets(user: CurrentUser = Depends(get_current_user)) -> list[DatasetInfo]:
    return service.list_datasets(user)


@router.get("/{dataset_id}", response_model=DatasetInfo, response_model_by_alias=True)
async def get_dataset(
    dataset_id: str, user: CurrentUser = Depends(get_current_user)
) -> DatasetInfo:
    return service.get_dataset_info(dataset_id, user)


@router.get("/{dataset_id}/schema", response_model=DatasetSchemaResponse)
async def get_dataset_schema(
    dataset_id: str, user: CurrentUser = Depends(get_current_user)
) -> DatasetSchemaResponse:
    return await service.get_dataset_schema(dataset_id, user)


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str, user: CurrentUser = Depends(get_current_user)) -> None:
    service.delete_dataset(dataset_id, user)


@router.patch("/{dataset_id}", response_model=DatasetInfo, response_model_by_alias=True)
async def update_dataset(
    dataset_id: str,
    request: UpdateDatasetRequest,
    user: CurrentUser = Depends(get_current_user),
) -> DatasetInfo:
    return service.update_dataset_metadata(dataset_id, request, user)


@router.post("/{dataset_id}/schema/review", response_model=DatasetSchemaResponse)
async def review_dataset_types(
    dataset_id: str,
    request: ReviewColumnsRequest = ReviewColumnsRequest(),
    user: CurrentUser = Depends(get_current_user),
) -> DatasetSchemaResponse:
    return await service.ai_review_column_types(dataset_id, request.columns, user)


@router.patch("/{dataset_id}/schema/columns/{column_name}", response_model=DatasetSchemaResponse)
async def update_column(
    dataset_id: str,
    column_name: str,
    request: UpdateColumnRequest,
    user: CurrentUser = Depends(get_current_user),
) -> DatasetSchemaResponse:
    return await service.update_column(
        dataset_id, column_name, category=request.category, alias=request.alias, user=user
    )


@router.post("/{dataset_id}/report-strategy", response_model=ReportStrategyResponse)
async def get_report_strategy(
    dataset_id: str,
    request: ReportStrategyRequest = ReportStrategyRequest(),
    user: CurrentUser = Depends(get_current_user),
) -> ReportStrategyResponse:
    return await service.generate_report_strategy(dataset_id, request.force, user)


@router.post("/{dataset_id}/insights", response_model=InsightsResponse)
async def get_chart_insights(
    dataset_id: str,
    request: GenerateInsightsRequest,
    user: CurrentUser = Depends(get_current_user),
) -> InsightsResponse:
    return await service.generate_chart_insights(dataset_id, request, user)
