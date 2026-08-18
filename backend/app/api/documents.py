from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ensure_entity_access, permitted_entity_ids, require_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import AuditArea, ChecklistItem, Document, Observation, User
from app.schemas import DocumentOut
from app.services.audit import record_audit

router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "text/plain",
}
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".docx", ".csv", ".txt"}


def storage_root() -> Path:
    root = Path(settings.upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def document_path(document: Document) -> Path:
    root = storage_root()
    path = (root / document.storage_key).resolve()
    if root not in path.parents:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Invalid document storage key")
    return path


@router.get("", response_model=list[DocumentOut])
def list_documents(
    entity_id: uuid.UUID | None = None,
    period: str | None = None,
    user: User = Depends(require_permission("VIEW_DOCUMENT")),
    db: Session = Depends(get_db),
):
    stmt = select(Document).where(
        Document.organization_id == user.organization_id, Document.is_active.is_(True)
    )
    allowed = permitted_entity_ids(user)
    if allowed is not None:
        stmt = stmt.where(Document.entity_id.in_(allowed))
    if entity_id:
        stmt = stmt.where(Document.entity_id == entity_id)
    if period:
        stmt = stmt.where(Document.period == period)
    return db.scalars(stmt.order_by(Document.created_at.desc())).all()


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    entity_id: uuid.UUID = Form(...),
    period: str = Form(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    document_type: str = Form(..., min_length=1, max_length=100),
    remarks: str = Form("", max_length=4000),
    audit_area_id: uuid.UUID | None = Form(None),
    observation_id: uuid.UUID | None = Form(None),
    checklist_item_id: uuid.UUID | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("UPLOAD_DOCUMENT")),
    db: Session = Depends(get_db),
):
    entity = ensure_entity_access(db, entity_id, user)
    if audit_area_id:
        area = db.get(AuditArea, audit_area_id)
        if not area or area.organization_id != user.organization_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit area not found")
    if observation_id:
        observation = db.get(Observation, observation_id)
        if (
            not observation
            or observation.organization_id != user.organization_id
            or observation.entity_id != entity.id
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Observation not found")
    if checklist_item_id:
        checklist = db.get(ChecklistItem, checklist_item_id)
        checklist_area = db.get(AuditArea, checklist.audit_area_id) if checklist else None
        if (
            not checklist
            or not checklist_area
            or checklist_area.organization_id != user.organization_id
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist item not found")
        if audit_area_id and checklist.audit_area_id != audit_area_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Checklist item and area differ"
            )

    original_name = Path(file.filename or "document").name
    extension = Path(original_name).suffix.lower()
    mime_type = (file.content_type or "application/octet-stream").lower()
    if extension not in ALLOWED_EXTENSIONS or mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Unsupported document type")

    storage_key = f"{user.organization_id}/{period}/{uuid.uuid4()}{extension}"
    destination = storage_root() / storage_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256()
    size = 0
    try:
        with destination.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "Document exceeds the upload limit",
                    )
                checksum.update(chunk)
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    document = Document(
        organization_id=user.organization_id,
        entity_id=entity_id,
        audit_area_id=audit_area_id,
        observation_id=observation_id,
        checklist_item_id=checklist_item_id,
        period=period,
        document_type=document_type,
        file_name=original_name,
        storage_key=storage_key,
        mime_type=mime_type,
        file_size=size,
        checksum=checksum.hexdigest(),
        remarks=remarks,
        uploaded_by_id=user.id,
    )
    db.add(document)
    db.flush()
    record_audit(
        db,
        user,
        "DOCUMENT_UPLOADED",
        "document",
        document.id,
        new_value={"file_name": original_name, "checksum": document.checksum, "file_size": size},
    )
    db.commit()
    db.refresh(document)
    return document


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    user: User = Depends(require_permission("DOWNLOAD_DOCUMENT")),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document or not document.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    ensure_entity_access(db, document.entity_id, user)
    path = document_path(document)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stored file is unavailable")
    record_audit(db, user, "DOCUMENT_DOWNLOADED", "document", document.id)
    db.commit()
    return FileResponse(path, media_type=document.mime_type, filename=document.file_name)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_document(
    document_id: uuid.UUID,
    user: User = Depends(require_permission("UPLOAD_DOCUMENT")),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document or not document.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    ensure_entity_access(db, document.entity_id, user)
    document.is_active = False
    record_audit(db, user, "DOCUMENT_ARCHIVED", "document", document.id)
    db.commit()
