from fastapi import APIRouter, Depends, Query, UploadFile

from src.core.auth import CurrentUser, get_current_user
from src.datasets import service
from src.datasets.schemas import (
    AcceptReplacementRequest,
    AcceptValueMergeRequest,
    AcceptValueMergeResponse,
    AddTagChartRequest,
    ChartRecommendation,
    ColumnValuesResponse,
    CustomChartRequest,
    DatasetInfo,
    DatasetSchemaResponse,
    GenerateInsightsRequest,
    InsightsResponse,
    ReorderChartsRequest,
    ReportStrategyRequest,
    ReportStrategyResponse,
    ReviewColumnsRequest,
    SuggestValueMergeRequest,
    TagCandidatesResponse,
    UpdateChartRequest,
    UpdateColumnRequest,
    UpdateDatasetRequest,
    UpdateTagConfigRequest,
    UploadResponse,
    ValueMergeSuggestion,
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


@router.get(
    "/{dataset_id}/schema/columns/{column_name}/values", response_model=ColumnValuesResponse
)
async def get_column_values(
    dataset_id: str,
    column_name: str,
    user: CurrentUser = Depends(get_current_user),
) -> ColumnValuesResponse:
    return await service.get_column_values(dataset_id, column_name, user)


@router.post(
    "/{dataset_id}/schema/columns/{column_name}/merge/suggest", response_model=ValueMergeSuggestion
)
async def suggest_column_value_merge(
    dataset_id: str,
    column_name: str,
    request: SuggestValueMergeRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ValueMergeSuggestion:
    return await service.suggest_value_merge_for_column(dataset_id, column_name, request.command, user)


@router.post(
    "/{dataset_id}/schema/columns/{column_name}/merge/accept", response_model=AcceptValueMergeResponse
)
async def accept_column_value_merge(
    dataset_id: str,
    column_name: str,
    request: AcceptValueMergeRequest,
    user: CurrentUser = Depends(get_current_user),
) -> AcceptValueMergeResponse:
    return await service.accept_value_merge(dataset_id, column_name, request.groups, user)


@router.delete(
    "/{dataset_id}/schema/columns/{column_name}/merge", response_model=ColumnValuesResponse
)
async def revert_column_value_merge(
    dataset_id: str,
    column_name: str,
    target: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
) -> ColumnValuesResponse:
    # `target` is a query param, not a path segment -- a merge target/source
    # can itself contain "/" (see the replace feature's own example, "Delhi /
    # NCR"), which a path segment can't reliably carry even URL-encoded.
    return await service.revert_value_merge(dataset_id, column_name, target, user)


@router.post(
    "/{dataset_id}/schema/columns/{column_name}/replace/accept", response_model=AcceptValueMergeResponse
)
async def accept_column_value_replacement(
    dataset_id: str,
    column_name: str,
    request: AcceptReplacementRequest,
    user: CurrentUser = Depends(get_current_user),
) -> AcceptValueMergeResponse:
    return await service.accept_value_replacement(dataset_id, column_name, request.find, request.replace, user)


@router.delete(
    "/{dataset_id}/schema/columns/{column_name}/replace", response_model=ColumnValuesResponse
)
async def revert_column_value_replacement(
    dataset_id: str,
    column_name: str,
    find: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
) -> ColumnValuesResponse:
    return await service.revert_value_replacement(dataset_id, column_name, find, user)


@router.get(
    "/{dataset_id}/schema/columns/{column_name}/tags", response_model=TagCandidatesResponse
)
async def get_column_tag_candidates(
    dataset_id: str,
    column_name: str,
    user: CurrentUser = Depends(get_current_user),
) -> TagCandidatesResponse:
    return await service.get_tag_candidates(dataset_id, column_name, user)


@router.put(
    "/{dataset_id}/schema/columns/{column_name}/tags/config", response_model=TagCandidatesResponse
)
async def update_column_tag_config(
    dataset_id: str,
    column_name: str,
    request: UpdateTagConfigRequest,
    user: CurrentUser = Depends(get_current_user),
) -> TagCandidatesResponse:
    return await service.update_tag_config(dataset_id, column_name, request, user)


@router.post(
    "/{dataset_id}/schema/columns/{column_name}/tags/chart", response_model=ChartRecommendation
)
async def add_column_tag_chart(
    dataset_id: str,
    column_name: str,
    request: AddTagChartRequest = AddTagChartRequest(),
    user: CurrentUser = Depends(get_current_user),
) -> ChartRecommendation:
    return await service.add_tag_chart(dataset_id, column_name, request.title, user)


@router.post("/{dataset_id}/report-strategy", response_model=ReportStrategyResponse)
async def get_report_strategy(
    dataset_id: str,
    request: ReportStrategyRequest = ReportStrategyRequest(),
    user: CurrentUser = Depends(get_current_user),
) -> ReportStrategyResponse:
    return await service.generate_report_strategy(dataset_id, request.force, user)


@router.post("/{dataset_id}/report-strategy/custom", response_model=ChartRecommendation)
async def add_custom_chart(
    dataset_id: str,
    request: CustomChartRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ChartRecommendation:
    return await service.add_custom_chart(dataset_id, request.prompt, user)


@router.delete("/{dataset_id}/report-strategy/{chart_id}", response_model=ReportStrategyResponse)
async def delete_chart(
    dataset_id: str,
    chart_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ReportStrategyResponse:
    return service.remove_chart(dataset_id, chart_id, user)


@router.patch("/{dataset_id}/report-strategy/{chart_id}", response_model=ChartRecommendation)
async def update_chart(
    dataset_id: str,
    chart_id: str,
    request: UpdateChartRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ChartRecommendation:
    return service.update_chart(dataset_id, chart_id, request, user)


@router.put("/{dataset_id}/report-strategy/order", response_model=ReportStrategyResponse)
async def reorder_charts(
    dataset_id: str,
    request: ReorderChartsRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ReportStrategyResponse:
    return service.reorder_charts(dataset_id, request.chart_ids, user)


@router.post("/{dataset_id}/insights", response_model=InsightsResponse)
async def get_chart_insights(
    dataset_id: str,
    request: GenerateInsightsRequest,
    user: CurrentUser = Depends(get_current_user),
) -> InsightsResponse:
    return await service.generate_chart_insights(dataset_id, request, user)
