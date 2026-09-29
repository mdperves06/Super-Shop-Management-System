"""CSV import with full validation before anything is written."""

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.models.auth import User
from app.models.catalog import Product, ProductBarcode, ProductBrand, ProductCategory, ProductUnit
from app.models.customers import Customer
from app.models.enums import AdjustmentType, LedgerType
from app.models.purchasing import Supplier
from app.schemas.catalog import ProductCreate
from app.schemas.customers import CustomerCreate
from app.schemas.purchasing import SupplierCreate
from app.services import audit, catalog_service, inventory_service, ledger, numbering

MAX_ROWS = 5000
MAX_BYTES = 2 * 1024 * 1024
TRUE = {"1", "true", "yes", "y", "t"}

TEMPLATES = {
    "products": ["sku", "name", "name_bn", "barcode", "category", "brand", "unit", "purchase_price", "selling_price", "mrp", "reorder_level",
                 "min_stock", "track_expiry", "opening_stock", "description"],
    "customers": ["name", "phone", "email", "address", "customer_type", "credit_limit", "opening_balance", "discount_percent"],
    "suppliers": ["name", "company", "phone", "email", "address", "contact_person", "tax_id", "payment_terms_days", "opening_balance"],
}
REQUIRED = {"products": ["sku", "name", "unit", "selling_price"], "customers": ["name"], "suppliers": ["name"]}


@dataclass
class ImportResult:
    total_rows: int = 0
    valid_rows: int = 0
    imported: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    committed: bool = False


def parse_csv(raw: bytes, kind: str) -> list[dict[str, str]]:
    if len(raw) > MAX_BYTES:
        raise ValidationFailed(f"CSV is too large (max {MAX_BYTES // 1024 // 1024} MB)", code="file_too_large")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationFailed("The file must be UTF-8 encoded CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationFailed("The CSV file is empty")
    headers = [h.strip().lower() for h in reader.fieldnames]
    missing = [c for c in REQUIRED[kind] if c not in headers]
    if missing:
        raise ValidationFailed(f"Missing required column(s): {', '.join(missing)}", code="missing_columns")
    unknown = [h for h in headers if h not in TEMPLATES[kind]]
    if unknown:
        raise ValidationFailed(f"Unknown column(s): {', '.join(unknown)}. Download the template for the accepted columns.", code="unknown_columns")
    rows = []
    for raw_row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
        if any(row.values()):
            rows.append(row)
    if len(rows) > MAX_ROWS:
        raise ValidationFailed(f"Too many rows (max {MAX_ROWS} per import)")
    return rows


def _dec(row: dict[str, str], key: str, default: str = "0") -> Decimal:
    v = row.get(key, "") or default
    try:
        return Decimal(v.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"{key}: '{v}' is not a number") from exc


def _err(result: ImportResult, line: int, message: str, value: str = "") -> None:
    result.errors.append({"row": line, "message": message, "value": value})


def _pydantic_msg(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())


def run(db: Session, kind: str, raw: bytes, user: User, *, dry_run: bool, skip_invalid: bool) -> ImportResult:
    rows = parse_csv(raw, kind)
    result = ImportResult(total_rows=len(rows))
    handler = {"products": _product, "customers": _customer, "suppliers": _supplier}[kind]
    seen: set[str] = set()
    staged: list[Any] = []
    for i, row in enumerate(rows, start=2):  # header is line 1
        try:
            item = handler(db, row, seen, user)
            staged.append((i, item))
        except ValidationError as exc:
            _err(result, i, _pydantic_msg(exc))
        except (ValueError, ValidationFailed) as exc:
            _err(result, i, getattr(exc, "message", str(exc)))
    result.valid_rows = len(staged)
    if dry_run or (result.errors and not skip_invalid):
        return result
    for line, item in staged:
        try:
            with db.begin_nested():
                _apply(db, kind, item, user)
            result.imported += 1
        except Exception as exc:  # noqa: BLE001 - reported per row, other rows continue
            _err(result, line, getattr(exc, "message", "Could not save this row"))
    audit.record(db, user=user, action=f"import.{kind}", entity=kind, new={"imported": result.imported, "errors": len(result.errors)})
    result.committed = True
    return result


def _product(db: Session, row: dict[str, str], seen: set[str], user: User) -> dict[str, Any]:
    sku = row.get("sku", "")
    if sku.lower() in seen:
        raise ValueError(f"Duplicate SKU '{sku}' inside the file")
    seen.add(sku.lower())
    barcode = row.get("barcode") or None
    if barcode:
        key = f"bc:{barcode}"
        if key in seen:
            raise ValueError(f"Duplicate barcode '{barcode}' inside the file")
        seen.add(key)
    unit_name = row.get("unit", "")
    unit = db.scalar(select(ProductUnit).where(func.lower(ProductUnit.name) == unit_name.lower())) or \
        db.scalar(select(ProductUnit).where(func.lower(ProductUnit.short_name) == unit_name.lower()))
    if unit is None:
        raise ValueError(f"unit: '{unit_name}' does not exist")
    opening = _dec(row, "opening_stock")
    if opening < 0:
        raise ValueError("opening_stock cannot be negative")
    if opening > 0 and "inventory.adjust" not in user.permission_codes:
        raise ValueError("opening_stock requires the inventory.adjust permission")
    data = ProductCreate(
        sku=sku, name=row.get("name", ""), name_bn=row.get("name_bn") or None, description=row.get("description") or None, unit_id=unit.id,
        purchase_price=_dec(row, "purchase_price") if "product.cost" in user.permission_codes else Decimal("0"),
        selling_price=_dec(row, "selling_price"), mrp=_dec(row, "mrp") if row.get("mrp") else None,
        reorder_level=_dec(row, "reorder_level"), min_stock=_dec(row, "min_stock"),
        track_expiry=row.get("track_expiry", "").lower() in TRUE, barcode=barcode)
    from sqlalchemy.exc import SQLAlchemyError  # noqa: F401

    if db.scalar(select(Product.id).where(func.lower(Product.sku) == sku.lower())):
        raise ValueError(f"SKU '{sku}' already exists")
    if barcode and db.scalar(select(ProductBarcode.id).where(ProductBarcode.barcode == barcode)):
        raise ValueError(f"Barcode '{barcode}' already exists")
    if data.track_expiry and opening > 0:
        raise ValueError("opening_stock cannot be imported for expiry-tracked products (needs an expiry date); receive it via a purchase")
    return {"data": data, "category": row.get("category") or None, "brand": row.get("brand") or None, "opening": opening}


def _customer(db: Session, row: dict[str, str], seen: set[str], user: User) -> CustomerCreate:
    phone = row.get("phone") or None
    if phone:
        if phone in seen:
            raise ValueError(f"Duplicate phone '{phone}' inside the file")
        seen.add(phone)
        if db.scalar(select(Customer.id).where(Customer.phone == phone)):
            raise ValueError(f"A customer with phone '{phone}' already exists")
    return CustomerCreate(
        name=row.get("name", ""), phone=phone, email=row.get("email") or None, address=row.get("address") or None,
        customer_type=(row.get("customer_type") or "RETAIL").upper(), credit_limit=_dec(row, "credit_limit"),
        opening_balance=_dec(row, "opening_balance"), discount_percent=_dec(row, "discount_percent"))


def _supplier(db: Session, row: dict[str, str], seen: set[str], user: User) -> SupplierCreate:
    phone = row.get("phone") or None
    if phone:
        if phone in seen:
            raise ValueError(f"Duplicate phone '{phone}' inside the file")
        seen.add(phone)
        if db.scalar(select(Supplier.id).where(Supplier.phone == phone, Supplier.is_deleted.is_(False))):
            raise ValueError(f"A supplier with phone '{phone}' already exists")
    return SupplierCreate(
        name=row.get("name", ""), company=row.get("company") or None, phone=phone, email=row.get("email") or None, address=row.get("address") or None,
        contact_person=row.get("contact_person") or None, tax_id=row.get("tax_id") or None,
        payment_terms_days=int(_dec(row, "payment_terms_days")), opening_balance=_dec(row, "opening_balance"))


def _named(db: Session, model: Any, name: str | None, *, parent: bool = False) -> int | None:
    if not name:
        return None
    stmt = select(model).where(func.lower(model.name) == name.lower())
    if model is ProductCategory:
        stmt = stmt.where(ProductCategory.parent_id.is_(None), ProductCategory.is_deleted.is_(False))
    else:
        stmt = stmt.where(model.is_deleted.is_(False))
    row = db.scalar(stmt)
    if row is None:
        row = model(name=name)
        db.add(row)
        db.flush()
    return row.id


def _apply(db: Session, kind: str, item: Any, user: User) -> None:
    if kind == "products":
        data: ProductCreate = item["data"]
        data.category_id = _named(db, ProductCategory, item["category"])
        data.brand_id = _named(db, ProductBrand, item["brand"])
        product = catalog_service.create_product(db, data, user)
        if item["opening"] > 0:
            inventory_service.adjust_stock(db, product, AdjustmentType.IN, item["opening"], "Opening stock (CSV import)", user,
                                           unit_cost=data.purchase_price)
    elif kind == "customers":
        c = Customer(code=numbering.next_number(db, "CUS", width=5), balance=0, **item.model_dump(exclude={"opening_balance"}),
                     opening_balance=item.opening_balance)
        db.add(c)
        db.flush()
        if item.opening_balance:
            ledger.post_customer(db, c.id, LedgerType.OPENING.value, item.opening_balance, user=user, notes="Opening balance (import)")
    else:
        s = Supplier(code=numbering.next_number(db, "SUP", width=4), balance=0, **item.model_dump(exclude={"opening_balance"}),
                     opening_balance=item.opening_balance)
        db.add(s)
        db.flush()
        if item.opening_balance:
            ledger.post_supplier(db, s.id, LedgerType.OPENING.value, item.opening_balance, user=user, notes="Opening balance (import)")
