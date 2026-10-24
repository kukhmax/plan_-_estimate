"""Onboarding API schemas (V2-3)."""
import uuid

from pydantic import BaseModel


class ExampleStatus(BaseModel):
    """The example object of the account: `project_id` is null when there is none."""

    project_id: uuid.UUID | None
    client_id: uuid.UUID | None


class ExampleCreated(ExampleStatus):
    created: bool


class ExampleRemoved(BaseModel):
    removed_project: bool
    removed_client: bool
