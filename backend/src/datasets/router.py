from fastapi import APIRouter, Depends, UploadFile

from src.core.auth import CurrentUser, get_current_user
from src.datasets import service
from src.datasets.schemas import DatasetInfo, UploadResponse

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


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str, user: CurrentUser = Depends(get_current_user)) -> None:
    service.delete_dataset(dataset_id, user)
