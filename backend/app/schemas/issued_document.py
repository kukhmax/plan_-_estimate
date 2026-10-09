"""Schemas of the document journal and issuing API (Stage 15F)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class IssueDocumentRequest(BaseModel):
    """What to issue. A technological card and a production plan are the whole object (no other fields). An estimate is named by its id; a photo report is the whole object or, when it is too big, a part: the
    chosen rooms (the general photos of the object come along only when asked for)."""

    kind: Literal["ESTIMATE", "PHOTO_REPORT", "TECH_CARD", "PRODUCTION_PLAN"]
    estimate_id: uuid.UUID | None = None
    room_ids: list[uuid.UUID] | None = None
    include_project_photos: bool | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _kind_fits_fields(self) -> "IssueDocumentRequest":
        if self.kind in ("TECH_CARD", "PRODUCTION_PLAN"):
            if self.estimate_id is not None or self.room_ids is not None or self.include_project_photos is not None:
                raise ValueError("a technological card and a production plan take no other fields")
        elif self.kind == "ESTIMATE":
            if self.estimate_id is None:
                raise ValueError("estimate_id is required for an estimate")
            if self.room_ids is not None or self.include_project_photos is not None:
                raise ValueError("room_ids and include_project_photos belong to a photo report")
        else:
            if self.estimate_id is not None:
                raise ValueError("estimate_id belongs to an estimate")
            if self.room_ids is not None and not self.room_ids:
                raise ValueError("room_ids must not be empty (leave it out for the whole report)")
            if self.room_ids is None and self.include_project_photos is not None:
                raise ValueError("include_project_photos only makes sense together with room_ids")
        return self


class IssuedDocumentRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: Literal["ESTIMATE", "PHOTO_REPORT", "TECH_CARD", "PRODUCTION_PLAN"]
    source_id: uuid.UUID | None
    source_version: int | None
    title: str
    number: str
    project_seq: int
    template_version: str
    status: Literal["PENDING", "SENT", "FAILED"]
    error_code: str | None
    scope: dict | None
    pages: int | None
    byte_size: int | None
    issued_at: datetime
    sent_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class IssuedDocumentListResponse(BaseModel):
    items: list[IssuedDocumentRead]
    total: int


class PreviewResponse(BaseModel):
    sent: bool
    pages: int
    byte_size: int


class RoomSummaryRead(BaseModel):
    room_id: uuid.UUID
    name: str
    photos: int
    has_inspection_content: bool

    model_config = ConfigDict(from_attributes=True)


class UnpricedWorkRead(BaseModel):
    """A recommended extra work without a price in the current estimate (it blocks the photo report), and where to fix it."""

    room_id: uuid.UUID
    room_name: str
    surface_id: uuid.UUID
    surface_name: str
    surface_type: str  # WALL | CEILING | FLOOR (the screen localizes generated names)
    work_code: str
    work_display_name: str | None
    work_name_key: str | None
    reason: str  # PENDING | NO_ESTIMATE | NOT_IN_ESTIMATE | NO_PRICE
    inspection_id: uuid.UUID | None
    inspection_surface_id: uuid.UUID | None
    inspection_plane: str | None  # FLOOR | CEILING | None

    model_config = ConfigDict(from_attributes=True)


class PhotoReportSummaryRead(BaseModel):
    photo_count: int
    project_photos: int
    limit: int
    over_limit: bool
    has_content: bool
    rooms: list[RoomSummaryRead]
    recommended_count: int  # recommended extra works the report would list
    unpriced_works: list[str]  # those without a price in the current estimate: they block issuing
    unpriced_items: list[UnpricedWorkRead]  # the same, structured (Stage 15H.1)
    estimate_id: uuid.UUID | None  # the current estimate (whose prices are used), None = the object has none
    estimate_status: str | None  # DRAFT | FINAL | ACCEPTED
