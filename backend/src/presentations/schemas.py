from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from src.query.schemas import QueryResponse


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    id: str
    title: str
    chart_type: str
    partition_type: str
    column: str
    result: QueryResponse


class InsightsBlock(BaseModel):
    type: Literal["insights"] = "insights"
    id: str
    chart_title: str
    bullets: list[str]


class TextBlock(BaseModel):
    """A manually-authored note -- the one block type that isn't pinned from
    the report-strategy feed, so a presentation isn't limited to just charts
    and AI insights."""

    type: Literal["text"] = "text"
    id: str
    text: str


PresentationBlock = Annotated[Union[ChartBlock, InsightsBlock, TextBlock], Field(discriminator="type")]


class PresentationPage(BaseModel):
    id: str
    title: str
    blocks: list[PresentationBlock] = []


class Presentation(BaseModel):
    dataset_id: str
    title: str
    pages: list[PresentationPage] = []
    updated_at: str | None = None


class PinChartInput(BaseModel):
    id: str
    title: str
    chart_type: str
    partition_type: str
    column: str
    result: QueryResponse


class PinBlockRequest(BaseModel):
    """Pinning always adds a chart block; insights are included alongside it
    only if the caller had already generated them for that chart."""

    chart: PinChartInput
    insights: list[str] | None = None


class UpdatePresentationRequest(BaseModel):
    title: str
    pages: list[PresentationPage]
