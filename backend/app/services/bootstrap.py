"""Idempotent reference data required by every deployment (not demo data)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import DEFAULT_ROLES, PERMISSIONS
from app.models.auth import Permission, Role
from app.models.catalog import ProductUnit, TaxRate
from app.models.finance import CashRegister, ExpenseCategory, PaymentMethod
from app.services import settings_service

UNITS = [
    ("Piece", "pc", False), ("Kilogram", "kg", True), ("Gram", "g", True), ("Liter", "L", True),
    ("Milliliter", "ml", True), ("Box", "box", False), ("Packet", "pkt", False), ("Bottle", "btl", False),
    ("Carton", "ctn", False), ("Dozen", "dz", False),
]

PAYMENT_METHODS = [
    ("CASH", "Cash", "CASH", False, 1),
    ("CARD", "Card", "CARD", True, 2),
    ("BKASH", "bKash", "MOBILE", True, 3),
    ("NAGAD", "Nagad", "MOBILE", True, 4),
    ("ROCKET", "Rocket", "MOBILE", True, 5),
    ("BANK", "Bank Transfer", "BANK", True, 6),
    ("OTHER", "Other", "OTHER", False, 7),
]

EXPENSE_CATEGORIES = [
    "Rent", "Electricity", "Internet", "Transport", "Salary", "Maintenance", "Marketing", "Packaging", "Other",
]


def sync_permissions_and_roles(db: Session, *, reset_system_roles: bool = False) -> None:
    perms = {p.code: p for p in db.scalars(select(Permission))}
    fresh: set[str] = set()
    for module, group in PERMISSIONS.items():
        for code, desc in group.items():
            if code not in perms:
                perms[code] = Permission(code=code, module=module, description=desc)
                db.add(perms[code])
                fresh.add(code)
            else:
                perms[code].module, perms[code].description = module, desc
    db.flush()

    roles = {r.name: r for r in db.scalars(select(Role))}
    for name, spec in DEFAULT_ROLES.items():
        role = roles.get(name)
        if role is None:
            role = Role(name=name, description=spec["description"], is_system=True)
            role.permissions = [perms[c] for c in dict.fromkeys(spec["permissions"])]
            db.add(role)
        elif name == "SUPER_ADMIN":
            role.permissions = list(perms.values())  # always tracks the full catalogue
        elif reset_system_roles:
            role.permissions = [perms[c] for c in dict.fromkeys(spec["permissions"])]
        else:  # upgrade path: newly introduced permissions reach the default roles without wiping local customisations
            have = {p.code for p in role.permissions}
            role.permissions.extend(perms[c] for c in dict.fromkeys(spec["permissions"]) if c in fresh and c not in have)
    db.flush()


def ensure_reference_data(db: Session) -> None:
    sync_permissions_and_roles(db)
    settings_service.ensure_defaults(db)

    if not db.scalar(select(ProductUnit.id).limit(1)):
        db.add_all(ProductUnit(name=n, short_name=s, allow_decimal=d) for n, s, d in UNITS)
    if not db.scalar(select(PaymentMethod.id).limit(1)):
        db.add_all(
            PaymentMethod(code=c, name=n, method_type=t, requires_reference=r, sort_order=o)
            for c, n, t, r, o in PAYMENT_METHODS
        )
    if not db.scalar(select(ExpenseCategory.id).limit(1)):
        db.add_all(ExpenseCategory(name=n) for n in EXPENSE_CATEGORIES)
    if not db.scalar(select(TaxRate.id).limit(1)):
        db.add(TaxRate(name="VAT 15%", rate=Decimal("15"), effective_from=date(2000, 1, 1), is_default=True))
        db.add(TaxRate(name="No VAT", rate=Decimal("0"), effective_from=date(2000, 1, 1)))
    if not db.scalar(select(CashRegister.id).limit(1)):
        db.add(CashRegister(name="Main Counter", location="Front"))
    db.flush()
