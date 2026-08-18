from pydantic import BaseModel

from src.query.schemas import QueryResponse


class ChartShare(BaseModel):
    token: str
    title: str
    chart_type: str
    partition_type: str
    column: str
    result: QueryResponse
    created_at: str
