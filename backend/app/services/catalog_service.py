import random
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models.auth import User
from app.models.base import utcnow
from app.models.catalog import (
    Product,
    ProductBarcode,
    ProductBrand,
    ProductCategory,
    ProductUnit,
    TaxRate,
)
from app.models.inventory import Inventory
from app.models.purchasing import Supplier
from app.schemas.catalog import ProductCreate, ProductOut, ProductUpdate
from app.services import audit

PRICE_FIELDS = ["purchase_price", "selling_price", "mrp", "tax_rate_id", "discount_percent"]
AUDIT_FIELDS = ["sku", "name", "category_id", "brand_id", "unit_id", *PRICE_FIELDS, "reorder_level", "min_stock", "is_active"]


def ean13_check_digit(twelve: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(twelve))
    return str((10 - total % 10) % 10)


def generate_barcode(db: Session) -> str:
    """Internal-use EAN-13 (GS1 prefix 20-29 is reserved for in-store codes)."""
    for _ in range(50):
        body = "20" + "".join(random.choices("0123456789", k=10))
        code = body + ean13_check_digit(body)
        if not db.scalar(select(ProductBarcode.id).where(ProductBarcode.barcode == code)):
            return code
    raise RuntimeError("Could not generate a unique barcode")


def _ensure_refs(db: Session, data: dict[str, Any]) -> None:
    checks = [
        ("category_id", ProductCategory), ("subcategory_id", ProductCategory), ("brand_id", ProductBrand),
        ("unit_id", ProductUnit), ("tax_rate_id", TaxRate), ("supplier_id", Supplier),
    ]
    for field, model in checks:
        value = data.get(field)
        if value is not None and db.get(model, value) is None:
            raise ValidationFailed(f"Invalid {field.replace('_id', '')}: id {value} does not exist")


def _check_sku_free(db: Session, sku: str, exclude_id: int | None = None) -> None:
    stmt = select(Product.id).where(func.lower(Product.sku) == sku.lower())
    if exclude_id:
        stmt = stmt.where(Product.id != exclude_id)
    if db.scalar(stmt):
        raise ConflictError(f"SKU '{sku}' is already in use", code="duplicate_sku")


def _check_barcode_free(db: Session, barcode: str, exclude_product_id: int | None = None) -> None:
    row = db.scalar(select(ProductBarcode).where(ProductBarcode.barcode == barcode))
    if row and row.product_id != exclude_product_id:
        raise ConflictError(f"Barcode '{barcode}' is already assigned to another product", code="duplicate_barcode")


def create_product(db: Session, data: ProductCreate, user: User) -> Product:
    payload = data.model_dump(exclude={"barcode", "extra_barcodes", "barcode_format"})
    _ensure_refs(db, payload)
    _check_sku_free(db, data.sku)
    codes: list[str] = []
    if data.barcode:
        codes.append(data.barcode.strip())
    codes += [c.strip() for c in data.extra_barcodes if c.strip()]
    if len(set(codes)) != len(codes):
        raise ValidationFailed("The same barcode was entered more than once")
    for c in codes:
        _check_barcode_free(db, c)
    product = Product(**payload)
    for i, c in enumerate(codes):
        product.barcodes.append(ProductBarcode(barcode=c, format=data.barcode_format, is_primary=(i == 0)))
    product.inventory = Inventory()
    db.add(product)
    db.flush()
    audit.record(db, user=user, action="product.create", entity="product", entity_id=product.id,
                 new=audit.snapshot(product, AUDIT_FIELDS))
    return product


def update_product(db: Session, product: Product, data: ProductUpdate, user: User, can_cost: bool) -> Product:
    changes = data.model_dump(exclude_unset=True)
    barcode = changes.pop("barcode", None)
    if "purchase_price" in changes and not can_cost:
        from app.core.errors import PermissionDenied

        if changes["purchase_price"] != product.purchase_price:
            raise PermissionDenied("You do not have permission to change the purchase cost")
        changes.pop("purchase_price")
    for required in ("unit_id", "selling_price", "name", "sku"):
        if required in changes and changes[required] is None:
            raise ValidationFailed(f"{required} cannot be empty")
    _ensure_refs(db, changes)
    if "sku" in changes:
        _check_sku_free(db, changes["sku"], product.id)
    old = audit.snapshot(product, AUDIT_FIELDS)
    for k, v in changes.items():
        setattr(product, k, v)
    if product.max_stock is not None and product.max_stock < product.min_stock:
        raise ValidationFailed("max_stock must not be less than min_stock")
    if barcode is not None:
        barcode = barcode.strip()
        if barcode:
            _check_barcode_free(db, barcode, product.id)
            primary = next((b for b in product.barcodes if b.is_primary), None)
            if primary:
                primary.barcode = barcode
            else:
                product.barcodes.append(ProductBarcode(barcode=barcode, is_primary=True))
    new = audit.snapshot(product, AUDIT_FIELDS)
    price_changed = any(old[f] != new[f] for f in PRICE_FIELDS)
    if old != new:
        audit.record(
            db, user=user, action="product.price_change" if price_changed else "product.update",
            entity="product", entity_id=product.id, old=old, new=new,
        )
    db.flush()
    return product


def add_barcode(db: Session, product: Product, barcode: str, fmt: str, primary: bool, user: User) -> ProductBarcode:
    barcode = barcode.strip()
    _check_barcode_free(db, barcode)
    if primary:
        for b in product.barcodes:
            b.is_primary = False
    row = ProductBarcode(barcode=barcode, format=fmt, is_primary=primary or not product.barcodes)
    product.barcodes.append(row)
    audit.record(db, user=user, action="product.barcode_add", entity="product", entity_id=product.id, new={"barcode": barcode})
    db.flush()
    return row


def archive_product(db: Session, product: Product, user: User) -> None:
    inv = product.inventory
    if inv and (inv.current_stock != 0 or inv.damaged_stock != 0 or inv.expired_stock != 0):
        raise ConflictError(
            "This product still has stock on record. Adjust stock to zero before deleting it.", code="product_has_stock"
        )
    product.is_deleted, product.is_active, product.deleted_at = True, False, utcnow()
    audit.record(db, user=user, action="product.delete", entity="product", entity_id=product.id,
                 old=audit.snapshot(product, AUDIT_FIELDS))


def get_product(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if not p or p.is_deleted:
        raise NotFoundError("Product not found")
    return p


def find_by_code(db: Session, code: str) -> Product | None:
    """Exact barcode match first, then SKU (case-insensitive)."""
    code = code.strip()
    if not code:
        return None
    row = db.scalar(select(ProductBarcode).where(ProductBarcode.barcode == code))
    if row and not row.product.is_deleted:
        return row.product
    return db.scalar(select(Product).where(func.lower(Product.sku) == code.lower(), Product.is_deleted.is_(False)))


def to_out(product: Product, can_cost: bool) -> ProductOut:
    out = ProductOut.model_validate(product)
    if not can_cost:
        out.purchase_price = None
    return out


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0))
