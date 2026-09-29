from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, PlainSerializer

T = TypeVar("T")


def _dt(v: datetime) -> str:
    return v.isoformat() + "Z" if v.tzinfo is None else v.isoformat()


def _dec(v: Decimal) -> float:
    return float(v)


# All stored datetimes are UTC-naive; serialise with an explicit Z so browsers parse them correctly.
UTCDateTime = Annotated[datetime, PlainSerializer(_dt, return_type=str, when_used="json")]
# Money/quantities travel as JSON numbers; the backend stays the source of truth for arithmetic.
Num = Annotated[Decimal, PlainSerializer(_dec, return_type=float, when_used="json")]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class Message(BaseModel):
    message: str


class PageParams:
    def __init__(self, page: int = 1, page_size: int = 20, search: str | None = None, sort: str | None = None):
        self.page = max(page, 1)
        self.page_size = min(max(page_size, 1), 200)
        self.search = search.strip() if search else None
        self.sort = sort

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
