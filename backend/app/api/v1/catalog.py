from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import func, or_, select

from app.api.deps import DB, Pagination, has_permission, require
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models.auth import User
from app.models.catalog import (
    Product,
    ProductBarcode,
    ProductBrand,
    ProductCategory,
    ProductUnit,
    TaxRate,
)
from app.models.inventory import Inventory
from app.repositories.base import apply_sort, like, page_response, paginate
from app.schemas.catalog import (
    BarcodeIn,
    BarcodeOut,
    BrandIn,
    BrandOut,
    CategoryIn,
    CategoryOut,
    ProductCreate,
    ProductLookup,
    ProductOut,
    ProductUpdate,
    TaxRateIn,
    TaxRateOut,
    UnitIn,
    UnitOut,
)
from app.schemas.common import Message, Page
from app.services import audit, catalog_service, pricing
from app.utils.uploads import IMAGE_TYPES, save_upload

router = APIRouter(tags=["catalog"])
Reader = Annotated[User, Depends(require("product.read"))]
Manager = Annotated[User, Depends(require("category.manage"))]


# ---- categories -----------------------------------------------------------------------

@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: DB, _: Reader, include_inactive: bool = False):
    stmt = select(ProductCategory).where(ProductCategory.is_deleted.is_(False)).order_by(ProductCategory.name)
    if not include_inactive:
        stmt = stmt.where(ProductCategory.is_active.is_(True))
    return list(db.scalars(stmt))


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, request: Request, db: DB, user: Manager):
    if body.parent_id and not db.get(ProductCategory, body.parent_id):
        raise ValidationFailed("Parent category does not exist")
    dup = db.scalar(select(ProductCategory.id).where(
        func.lower(ProductCategory.name) == body.name.lower(), ProductCategory.parent_id == body.parent_id,
        ProductCategory.is_deleted.is_(False)))
    if dup:
        raise ConflictError("A category with this name already exists", code="duplicate_category")
    row = ProductCategory(**body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="category.create", entity="category", entity_id=row.id, new=body.model_dump(), request=request)
    db.commit()
    return row


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryIn, request: Request, db: DB, user: Manager):
    row = db.get(ProductCategory, category_id)
    if not row or row.is_deleted:
        raise NotFoundError("Category not found")
    if body.parent_id == category_id:
        raise ValidationFailed("A category cannot be its own parent")
    old = {"name": row.name, "parent_id": row.parent_id, "is_active": row.is_active}
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    audit.record(db, user=user, action="category.update", entity="category", entity_id=row.id, old=old, new=body.model_dump(), request=request)
    db.commit()
    return row


@router.delete("/categories/{category_id}", response_model=Message)
def delete_category(category_id: int, request: Request, db: DB, user: Manager):
    row = db.get(ProductCategory, category_id)
    if not row or row.is_deleted:
        raise NotFoundError("Category not found")
    in_use = db.scalar(select(func.count()).select_from(Product).where(
        or_(Product.category_id == category_id, Product.subcategory_id == category_id), Product.is_deleted.is_(False)))
    children = db.scalar(select(func.count()).select_from(ProductCategory).where(
        ProductCategory.parent_id == category_id, ProductCategory.is_deleted.is_(False)))
    if in_use or children:
        raise ConflictError("Category is in use by products or has sub-categories", code="category_in_use")
    row.is_deleted, row.is_active = True, False
    audit.record(db, user=user, action="category.delete", entity="category", entity_id=category_id, request=request)
    db.commit()
    return Message(message="Category deleted")


# ---- brands ---------------------------------------------------------------------------

@router.get("/brands", response_model=list[BrandOut])
def list_brands(db: DB, _: Reader):
    return list(db.scalars(select(ProductBrand).where(ProductBrand.is_deleted.is_(False)).order_by(ProductBrand.name)))


@router.post("/brands", response_model=BrandOut, status_code=201)
def create_brand(body: BrandIn, request: Request, db: DB, user: Manager):
    if db.scalar(select(ProductBrand.id).where(func.lower(ProductBrand.name) == body.name.lower())):
        raise ConflictError("A brand with this name already exists")
    row = ProductBrand(**body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="brand.create", entity="brand", entity_id=row.id, new=body.model_dump(), request=request)
    db.commit()
    return row


@router.put("/brands/{brand_id}", response_model=BrandOut)
def update_brand(brand_id: int, body: BrandIn, request: Request, db: DB, user: Manager):
    row = db.get(ProductBrand, brand_id)
    if not row or row.is_deleted:
        raise NotFoundError("Brand not found")
    clash = db.scalar(select(ProductBrand.id).where(func.lower(ProductBrand.name) == body.name.lower(), ProductBrand.id != brand_id))
    if clash:
        raise ConflictError("A brand with this name already exists")
    row.name, row.is_active = body.name, body.is_active
    audit.record(db, user=user, action="brand.update", entity="brand", entity_id=row.id, new=body.model_dump(), request=request)
    db.commit()
    return row


@router.delete("/brands/{brand_id}", response_model=Message)
def delete_brand(brand_id: int, request: Request, db: DB, user: Manager):
    row = db.get(ProductBrand, brand_id)
    if not row or row.is_deleted:
        raise NotFoundError("Brand not found")
    if db.scalar(select(func.count()).select_from(Product).where(Product.brand_id == brand_id, Product.is_deleted.is_(False))):
        raise ConflictError("Brand is used by products", code="brand_in_use")
    row.is_deleted, row.is_active = True, False
    audit.record(db, user=user, action="brand.delete", entity="brand", entity_id=brand_id, request=request)
    db.commit()
    return Message(message="Brand deleted")


# ---- units & tax ----------------------------------------------------------------------

@router.get("/units", response_model=list[UnitOut])
def list_units(db: DB, _: Reader):
    return list(db.scalars(select(ProductUnit).order_by(ProductUnit.id)))


@router.post("/units", response_model=UnitOut, status_code=201)
def create_unit(body: UnitIn, request: Request, db: DB, user: Manager):
    if db.scalar(select(ProductUnit.id).where(func.lower(ProductUnit.name) == body.name.lower())):
        raise ConflictError("A unit with this name already exists")
    row = ProductUnit(**body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="unit.create", entity="unit", entity_id=row.id, new=body.model_dump(), request=request)
    db.commit()
    return row


@router.put("/units/{unit_id}", response_model=UnitOut)
def update_unit(unit_id: int, body: UnitIn, request: Request, db: DB, user: Manager):
    row = db.get(ProductUnit, unit_id)
    if not row:
        raise NotFoundError("Unit not found")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    audit.record(db, user=user, action="unit.update", entity="unit", entity_id=row.id, new=body.model_dump(), request=request)
    db.commit()
    return row


@router.get("/tax-rates", response_model=list[TaxRateOut])
def list_tax_rates(db: DB, _: Reader):
    return list(db.scalars(select(TaxRate).order_by(TaxRate.id)))


@router.post("/tax-rates", response_model=TaxRateOut, status_code=201)
def create_tax_rate(body: TaxRateIn, request: Request, db: DB, user: Annotated[User, Depends(require("settings.update"))]):
    row = TaxRate(**body.model_dump())
    if body.is_default:
        for t in db.scalars(select(TaxRate).where(TaxRate.is_default.is_(True))):
            t.is_default = False
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="tax_rate.create", entity="tax_rate", entity_id=row.id, new=body.model_dump(), request=request)
    db.commit()
    return row


@router.put("/tax-rates/{tax_id}", response_model=TaxRateOut)
def update_tax_rate(tax_id: int, body: TaxRateIn, request: Request, db: DB, user: Annotated[User, Depends(require("settings.update"))]):
    row = db.get(TaxRate, tax_id)
    if not row:
        raise NotFoundError("Tax rate not found")
    old = {"name": row.name, "rate": row.rate, "is_active": row.is_active}
    if body.is_default:
        for t in db.scalars(select(TaxRate).where(TaxRate.is_default.is_(True), TaxRate.id != tax_id)):
            t.is_default = False
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    audit.record(db, user=user, action="tax_rate.update", entity="tax_rate", entity_id=row.id, old=old, new=body.model_dump(), request=request)
    db.commit()
    return row


# ---- products -------------------------------------------------------------------------

@router.get("/products", response_model=Page[ProductOut])
def list_products(
    db: DB, p: Pagination, user: Reader,
    category_id: int | None = None, brand_id: int | None = None, supplier_id: int | None = None,
    is_active: bool | None = None, stock_status: str | None = None,
):
    stmt = select(Product).where(Product.is_deleted.is_(False))
    if p.search:
        term = like(p.search)
        stmt = stmt.where(or_(
            Product.name.ilike(term, escape="\\"), Product.name_bn.ilike(term, escape="\\"),
            Product.sku.ilike(term, escape="\\"),
            Product.barcodes.any(ProductBarcode.barcode.ilike(term, escape="\\")),
        ))
    if category_id:
        ids = [category_id, *db.scalars(select(ProductCategory.id).where(ProductCategory.parent_id == category_id))]
        stmt = stmt.where(or_(Product.category_id.in_(ids), Product.subcategory_id.in_(ids)))
    if brand_id:
        stmt = stmt.where(Product.brand_id == brand_id)
    if supplier_id:
        stmt = stmt.where(Product.supplier_id == supplier_id)
    if is_active is not None:
        stmt = stmt.where(Product.is_active == is_active)
    if stock_status == "out":
        stmt = stmt.where(Product.inventory.has(Inventory.current_stock <= 0))
    elif stock_status == "low":
        stmt = stmt.where(Product.inventory.has(
            (Inventory.current_stock > 0) & (Inventory.current_stock <= Product.reorder_level)))
    elif stock_status == "in":
        stmt = stmt.where(Product.inventory.has(Inventory.current_stock > 0))
    stmt = apply_sort(stmt, Product, p.sort, {"name", "sku", "selling_price", "created_at"}, Product.name)
    rows, total = paginate(db, stmt, p)
    can_cost = has_permission(user, "product.cost")
    return page_response([catalog_service.to_out(r, can_cost) for r in rows], total, p)


@router.get("/products/lookup", response_model=list[ProductLookup])
def lookup_products(db: DB, user: Annotated[User, Depends(require("sale.create", "product.read", any_of=True))],
                    q: str = "", category_id: int | None = None, limit: int = 30):
    """Fast POS search: exact barcode/SKU hit first, otherwise name search."""
    limit = min(max(limit, 1), 100)
    products: list[Product] = []
    q = q.strip()
    exact = catalog_service.find_by_code(db, q) if q else None
    if exact and exact.is_active:
        products.append(exact)
    else:
        stmt = select(Product).where(Product.is_deleted.is_(False), Product.is_active.is_(True))
        if q:
            term = like(q)
            stmt = stmt.where(or_(Product.name.ilike(term, escape="\\"), Product.name_bn.ilike(term, escape="\\"),
                                  Product.sku.ilike(term, escape="\\"),
                                  Product.barcodes.any(ProductBarcode.barcode.ilike(term, escape="\\"))))
        if category_id:
            ids = [category_id, *db.scalars(select(ProductCategory.id).where(ProductCategory.parent_id == category_id))]
            stmt = stmt.where(or_(Product.category_id.in_(ids), Product.subcategory_id.in_(ids)))
        products = list(db.scalars(stmt.order_by(Product.name).limit(limit)).unique())
    return [pricing.to_lookup(db, p) for p in products]


@router.get("/products/generate-barcode")
def generate_barcode(db: DB, _: Annotated[User, Depends(require("product.create", "product.update", any_of=True))]):
    return {"barcode": catalog_service.generate_barcode(db), "format": "EAN13"}


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductCreate, request: Request, db: DB, user: Annotated[User, Depends(require("product.create"))]):
    if body.purchase_price and not has_permission(user, "product.cost"):
        body.purchase_price = type(body.purchase_price)("0")
    product = catalog_service.create_product(db, body, user)
    db.commit()
    return catalog_service.to_out(product, has_permission(user, "product.cost"))


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: DB, user: Reader):
    return catalog_service.to_out(catalog_service.get_product(db, product_id), has_permission(user, "product.cost"))


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductUpdate, request: Request, db: DB, user: Annotated[User, Depends(require("product.update"))]):
    product = catalog_service.get_product(db, product_id)
    can_cost = has_permission(user, "product.cost")
    catalog_service.update_product(db, product, body, user, can_cost)
    db.commit()
    return catalog_service.to_out(product, can_cost)


@router.delete("/products/{product_id}", response_model=Message)
def delete_product(product_id: int, request: Request, db: DB, user: Annotated[User, Depends(require("product.delete"))]):
    product = catalog_service.get_product(db, product_id)
    catalog_service.archive_product(db, product, user)
    db.commit()
    return Message(message="Product deleted")


@router.post("/products/{product_id}/image", response_model=ProductOut)
async def upload_image(product_id: int, db: DB, user: Annotated[User, Depends(require("product.update"))], file: UploadFile = File(...)):
    product = catalog_service.get_product(db, product_id)
    path, _, _, _ = await save_upload(file, subdir="products", allowed=IMAGE_TYPES)
    old = product.image_path
    product.image_path = path
    audit.record(db, user=user, action="product.image", entity="product", entity_id=product.id, old={"image": old}, new={"image": path})
    db.commit()
    return catalog_service.to_out(product, has_permission(user, "product.cost"))


@router.post("/products/{product_id}/barcodes", response_model=BarcodeOut, status_code=201)
def add_barcode(product_id: int, body: BarcodeIn, db: DB, user: Annotated[User, Depends(require("product.update"))]):
    product = catalog_service.get_product(db, product_id)
    row = catalog_service.add_barcode(db, product, body.barcode, body.format, body.is_primary, user)
    db.commit()
    return row


@router.delete("/products/{product_id}/barcodes/{barcode_id}", response_model=Message)
def remove_barcode(product_id: int, barcode_id: int, db: DB, user: Annotated[User, Depends(require("product.update"))]):
    product = catalog_service.get_product(db, product_id)
    row = next((b for b in product.barcodes if b.id == barcode_id), None)
    if not row:
        raise NotFoundError("Barcode not found")
    product.barcodes.remove(row)
    if row.is_primary and product.barcodes:
        product.barcodes[0].is_primary = True
    audit.record(db, user=user, action="product.barcode_remove", entity="product", entity_id=product.id, old={"barcode": row.barcode})
    db.commit()
    return Message(message="Barcode removed")
