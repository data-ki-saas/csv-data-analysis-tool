from pydantic import BaseModel

from src.query.schemas import QueryResponse
from src.settings.schemas import FooterPreset, HeaderPreset


class ChartShare(BaseModel):
    token: str
    title: str
    chart_type: str
    partition_type: str
    column: str
    result: QueryResponse
    created_at: str
    # Snapshotted from the owner's active presets at share-creation time (see
    # service.create_chart_share) -- the public viewer has no session to fetch
    # live settings with, and a later branding change shouldn't retroactively
    # alter links already shared.
    header_snapshot: HeaderPreset | None = None
    footer_snapshot: FooterPreset | None = None
