from pydantic import BaseModel


class QueryRequest(BaseModel):
    sql: str
    max_rows: int | None = None


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
