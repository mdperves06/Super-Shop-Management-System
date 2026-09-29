from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.schemas.common import PageParams

T = TypeVar("T")


def paginate(db: Session, stmt: Select[Any], params: PageParams, *, scalars: bool = True) -> tuple[list[Any], int]:
    """Runs a count query and a limited page query; never loads the whole table."""
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0
    page_stmt = stmt.offset(params.offset).limit(params.page_size)
    rows = db.scalars(page_stmt).unique().all() if scalars else db.execute(page_stmt).all()
    return list(rows), total


def page_response(items: list[Any], total: int, params: PageParams) -> dict[str, Any]:
    pages = max((total + params.page_size - 1) // params.page_size, 1)
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size, "pages": pages}


def apply_sort(stmt: Select[Any], model: Any, sort: str | None, allowed: set[str], default: Any) -> Select[Any]:
    """`sort=name` ascending, `sort=-name` descending; only whitelisted columns are honoured."""
    if sort:
        desc = sort.startswith("-")
        col = sort.lstrip("-")
        if col in allowed and hasattr(model, col):
            attr = getattr(model, col)
            return stmt.order_by(attr.desc() if desc else attr.asc())
    return stmt.order_by(default)


def like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
