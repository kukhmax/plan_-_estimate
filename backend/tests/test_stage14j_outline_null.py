"""Stage 14J — a cleared marker contour is SQL NULL, not the JSON value `null`.

Found by the PostgreSQL proof (tests/test_stage14j_postgres.py::test_a4): with the plain JSON type the ORM stores `None`
as the JSON document `null`, so `outline IS NULL` / `count(outline)` treated a cleared contour as a contour. The API read
the value back as None either way, which is why nothing visible was wrong; the column now persists None as SQL NULL
(`JSON(none_as_null=True)`: ORM behaviour only, no schema change, no migration).
"""

import uuid
from types import SimpleNamespace

from sqlalchemy import text

from app.domain.services.photo_annotation_service import PhotoAnnotationService
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import (
    PhotoAttachment,
    PhotoAttachmentContext,
    PhotoCategory,
)
from tests.test_estimates import _make_project, _make_room, _make_user
from tests.test_stage14b4_photo_asset import raw_asset


async def marker_world(db):
    user = await _make_user(db, 9201)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    asset = raw_asset(user, project, status=PhotoAssetStatus.READY)
    db.add(asset)
    await db.flush()
    attachment = PhotoAttachment(asset_id=asset.id, project_id=project.id, context=PhotoAttachmentContext.ROOM,
                                 room_id=room.id, category=PhotoCategory.GENERAL)
    db.add(attachment)
    await db.commit()
    return SimpleNamespace(owner=user.id, project=project.id, attachment=attachment.id)


async def is_sql_null(db, marker_id: uuid.UUID) -> bool:
    return (await db.execute(text("SELECT outline IS NULL FROM photo_annotations WHERE id = :i"),
                             {"i": marker_id.hex if db.bind.dialect.name == "sqlite" else marker_id})).scalar_one()


async def test_a_new_marker_and_a_cleared_contour_are_both_sql_null(db_session):
    w = await marker_world(db_session)
    service = PhotoAnnotationService(db_session)
    marker = await service.create(w.owner, w.project, w.attachment, x=0.2, y=0.2)
    assert await is_sql_null(db_session, marker.id)
    await service.update(w.owner, w.project, w.attachment, marker.id, outline=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.4]])
    assert not await is_sql_null(db_session, marker.id)
    cleared = await service.update(w.owner, w.project, w.attachment, marker.id, outline=None)
    assert cleared.outline is None
    assert await is_sql_null(db_session, marker.id)  # was the JSON text 'null' before the fix
    count = (await db_session.execute(text("SELECT count(outline) FROM photo_annotations"))).scalar_one()
    assert count == 0


async def test_the_column_type_persists_none_as_null():
    assert PhotoAnnotation.__table__.c.outline.type.none_as_null is True
