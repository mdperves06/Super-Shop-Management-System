from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.api.deps import DB, require
from app.core.errors import PermissionDenied, ValidationFailed
from app.models.auth import User
from app.schemas.common import Message
from app.services import audit, backup_service, import_service

router = APIRouter(prefix="/admin", tags=["admin"])
Importer = Annotated[User, Depends(require("import.manage", "product.import", "customer.import", any_of=True))]
BackupAdmin = Annotated[User, Depends(require("backup.manage"))]

IMPORT_PERMS = {"products": "product.import", "customers": "customer.import", "suppliers": "import.manage"}


@router.get("/import/{kind}/template")
def import_template(kind: str, user: Importer):
    if kind not in import_service.TEMPLATES:
        raise ValidationFailed("Unknown import type")
    header = ",".join(import_service.TEMPLATES[kind])
    return Response(("﻿" + header + "\n").encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{kind}-template.csv"'})


@router.post("/import/{kind}")
async def import_csv(kind: str, request: Request, db: DB, user: Importer, file: UploadFile = File(...),
                     dry_run: bool = Form(True), skip_invalid: bool = Form(False)):
    if kind not in import_service.TEMPLATES:
        raise ValidationFailed("Unknown import type")
    needed = IMPORT_PERMS[kind]
    if needed not in user.permission_codes and "import.manage" not in user.permission_codes:
        raise PermissionDenied("You do not have permission to import this data", details={"required": [needed]})
    raw = await file.read(import_service.MAX_BYTES + 1)
    result = import_service.run(db, kind, raw, user, dry_run=dry_run, skip_invalid=skip_invalid)
    if result.committed:
        db.commit()
    else:
        db.rollback()
    return {"total_rows": result.total_rows, "valid_rows": result.valid_rows, "imported": result.imported,
            "errors": result.errors[:200], "error_count": len(result.errors), "committed": result.committed, "dry_run": dry_run}


@router.get("/backups")
def list_backups(_: BackupAdmin):
    return backup_service.list_backups()


@router.post("/backups", status_code=201)
def create_backup(request: Request, db: DB, user: BackupAdmin):
    path = backup_service.create_backup()
    audit.record(db, user=user, action="backup.create", entity="backup", entity_id=path.name, request=request)
    db.commit()
    return {"name": path.name, "size": path.stat().st_size}


@router.get("/backups/{name}/download")
def download_backup(name: str, request: Request, db: DB, user: BackupAdmin):
    path = backup_service.resolve(name)
    audit.record(db, user=user, action="backup.download", entity="backup", entity_id=name, request=request)
    db.commit()
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


class RestoreIn(BaseModel):
    confirm: str = Field(description="Must equal the backup file name")


@router.post("/backups/{name}/restore", response_model=Message)
def restore_backup(name: str, body: RestoreIn, request: Request, db: DB, user: BackupAdmin):
    if body.confirm != name:
        raise ValidationFailed("Type the backup name to confirm the restore")
    audit.record(db, user=user, action="backup.restore", entity="backup", entity_id=name, request=request)
    db.commit()
    backup_service.restore_backup(name)
    return Message(message="Database restored. Sign in again; other users' sessions may need to refresh.")
