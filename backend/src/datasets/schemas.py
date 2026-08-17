from pydantic import BaseModel, ConfigDict, Field


class ColumnInfo(BaseModel):
    name: str
    type: str


class DatasetPreview(BaseModel):
    columns: list[str]
    rows: list[list]


class UploadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_id: str
    filename: str
    row_count: int
    schema_: list[ColumnInfo] = Field(alias="schema")
    preview: DatasetPreview


class DatasetInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_id: str
    filename: str
    row_count: int
    schema_: list[ColumnInfo] = Field(alias="schema")
