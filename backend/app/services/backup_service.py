"""Database backup / restore.

SQLite  : online backup through the sqlite3 backup API (consistent even while the app is running).
Postgres: pg_dump / pg_restore when the client tools are installed; otherwise the documented commands apply.
"""

import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.errors import AppError, NotFoundError, ValidationFailed

NAME_RE = re.compile(r"^shop-\d{8}-\d{6}(-[a-z]+)?\.(db|dump)$")


def backup_dir() -> Path:
    p = Path(settings.backup_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sqlite_path() -> Path:
    return Path(make_url(settings.database_url).database or "")


def create_backup(label: str = "") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = f"-{label}" if label else ""
    if settings.is_sqlite:
        target = backup_dir() / f"shop-{stamp}{suffix}.db"
        src = sqlite3.connect(_sqlite_path())
        try:
            dst = sqlite3.connect(target)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        return target
    target = backup_dir() / f"shop-{stamp}{suffix}.dump"
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise AppError("pg_dump is not installed on the server. Run: pg_dump -Fc \"$DATABASE_URL\" > backup.dump", code="backup_tool_missing")
    url = make_url(settings.database_url)
    env = {"PGPASSWORD": url.password or "", "PATH": str(Path(pg_dump).parent)}
    cmd = [pg_dump, "-Fc", "-h", url.host or "localhost", "-p", str(url.port or 5432), "-U", url.username or "", "-f", str(target), url.database or ""]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)  # noqa: S603
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        raise AppError("Backup failed. See server logs.", code="backup_failed")
    return target


def list_backups() -> list[dict]:
    out = []
    for f in sorted(backup_dir().iterdir(), reverse=True):
        if NAME_RE.match(f.name):
            st = f.stat()
            out.append({"name": f.name, "size": st.st_size, "created_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()})
    return out


def resolve(name: str) -> Path:
    if not NAME_RE.match(name):
        raise ValidationFailed("Invalid backup name")
    path = backup_dir() / name
    if not path.exists():
        raise NotFoundError("Backup not found")
    return path


def restore_backup(name: str) -> None:
    from app.core.database import engine

    path = resolve(name)
    if settings.is_sqlite:
        try:
            probe = sqlite3.connect(path)
            probe.execute("PRAGMA integrity_check").fetchone()
            probe.close()
        except sqlite3.DatabaseError as exc:
            raise ValidationFailed("That file is not a valid database backup") from exc
        create_backup("prerestore")  # safety copy of the current state
        engine.dispose()
        dst = _sqlite_path()
        for ext in ("-wal", "-shm"):
            Path(str(dst) + ext).unlink(missing_ok=True)
        shutil.copyfile(path, dst)
        engine.dispose()
        return
    pg_restore = shutil.which("pg_restore")
    if not pg_restore:
        raise AppError("pg_restore is not installed. Run: pg_restore --clean --if-exists -d \"$DATABASE_URL\" backup.dump", code="restore_tool_missing")
    create_backup("prerestore")
    url = make_url(settings.database_url)
    env = {"PGPASSWORD": url.password or "", "PATH": str(Path(pg_restore).parent)}
    cmd = [pg_restore, "--clean", "--if-exists", "-h", url.host or "localhost", "-p", str(url.port or 5432), "-U", url.username or "", "-d", url.database or "", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)  # noqa: S603
    engine.dispose()
    if result.returncode not in (0, 1):  # 1 = warnings only
        raise AppError("Restore failed. See server logs.", code="restore_failed")
