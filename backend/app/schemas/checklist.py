import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.checklist import AnswerType, Substrate


class ChecklistOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    key: str
    label_key: str
    finding_key: str | None = None


class ChecklistQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    key: str
    text_key: str
    hint_key: str | None = None
    unit_key: str | None = None
    answer_type: AnswerType
    finding_key: str | None = None
    options: list[ChecklistOptionRead] = []


class ChecklistSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    position: int
    title_key: str
    description_key: str | None = None
    questions: list[ChecklistQuestionRead] = []


class ChecklistTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    version: int
    substrate: Substrate | None = None
    title_key: str
    active: bool
    sections: list[ChecklistSectionRead] = []
    created_at: datetime
    updated_at: datetime


class ChecklistTemplateListResponse(BaseModel):
    items: list[ChecklistTemplateRead]
    total: int
