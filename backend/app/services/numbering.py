from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.system import NumberSequence


def next_number(db: Session, prefix: str, *, width: int = 6) -> str:
    """Gap-tolerant, collision-free document numbers, e.g. INV-2026-000001.

    The counter row is bumped with a single atomic UPDATE; concurrent transactions
    serialise on that row lock so two callers can never receive the same value.
    """
    year = datetime.now(timezone.utc).year
    for _ in range(3):
        result = db.execute(
            update(NumberSequence)
            .where(NumberSequence.prefix == prefix, NumberSequence.year == year)
            .values(last_value=NumberSequence.last_value + 1)
        )
        if result.rowcount == 1:
            value = db.scalar(
                select(NumberSequence.last_value).where(NumberSequence.prefix == prefix, NumberSequence.year == year)
            )
            return f"{prefix}-{year}-{value:0{width}d}"
        try:
            with db.begin_nested():
                db.execute(insert(NumberSequence).values(prefix=prefix, year=year, last_value=0))
        except IntegrityError:
            pass  # another transaction created it first; retry the UPDATE
    raise RuntimeError("Could not allocate document number")
