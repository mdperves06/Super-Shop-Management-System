"""Development / demo data.

    python seed.py            # seed an empty database
    python seed.py --reset    # SQLite only: delete the database file first, then seed

Everything is created through the same service layer the API uses, so stock ledgers, supplier and customer
balances, cash sessions and audit logs are internally consistent.

!! Demo passwords below are public and only for local development. Change or delete these users in production. !!
"""

import argparse
import random
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, update

from app.core.config import settings

DEMO_PASSWORD = "Demo@12345"

USERS = [
    ("superadmin@example.com", "Super Admin", "SUPER_ADMIN"),
    ("admin@example.com", "Rafiq Ahmed (Owner)", "ADMIN"),
    ("manager@example.com", "Nasrin Sultana", "MANAGER"),
    ("cashier@example.com", "Kamal Hossain", "CASHIER"),
    ("cashier2@example.com", "Sumaiya Akter", "CASHIER"),
    ("inventory@example.com", "Jahid Hasan", "INVENTORY_MANAGER"),
    ("accountant@example.com", "Farhana Islam", "ACCOUNTANT"),
    ("staff@example.com", "Milon Das", "STAFF"),
]

CATEGORIES = {
    "Grocery": "মুদি", "Beverage": "পানীয়", "Snacks": "স্ন্যাকস", "Personal Care": "ব্যক্তিগত যত্ন", "Cleaning": "পরিষ্কার",
    "Dairy": "দুগ্ধজাত", "Frozen Food": "হিমায়িত খাবার", "Bakery": "বেকারি", "Stationery": "স্টেশনারি", "Household": "গৃহস্থালি",
}

# name, bangla, category, brand, unit, cost, price, mrp, vat(15%?), reorder, expiry_days(None=no tracking), barcode
PRODUCTS = [
    ("Miniket Rice 5kg", "মিনিকেট চাল ৫ কেজি", "Grocery", "Rashid", "Packet", 380, 425, 430, False, 15, None),
    ("Nazirshail Rice 25kg", "নাজিরশাইল চাল ২৫ কেজি", "Grocery", "Rashid", "Packet", 1850, 2050, 2100, False, 5, None),
    ("Soyabean Oil 5L", "সয়াবিন তেল ৫ লিটার", "Grocery", "Teer", "Bottle", 780, 850, 870, True, 10, 365),
    ("Soyabean Oil 1L", "সয়াবিন তেল ১ লিটার", "Grocery", "Teer", "Bottle", 165, 182, 185, True, 30, 365),
    ("Masoor Dal 1kg", "মসুর ডাল ১ কেজি", "Grocery", "Radhuni", "Packet", 118, 135, 140, False, 25, None),
    ("Sugar 1kg", "চিনি ১ কেজি", "Grocery", "Local", "Packet", 122, 135, 140, False, 40, None),
    ("Iodized Salt 1kg", "আয়োডিন লবণ ১ কেজি", "Grocery", "Ispahani", "Packet", 38, 45, 48, False, 40, None),
    ("Turmeric Powder 200g", "হলুদ গুঁড়া ২০০ গ্রাম", "Grocery", "Radhuni", "Packet", 68, 82, 85, True, 20, 300),
    ("Chili Powder 200g", "মরিচ গুঁড়া ২০০ গ্রাম", "Grocery", "Radhuni", "Packet", 88, 105, 110, True, 20, 300),
    ("Mineral Water 1.5L", "মিনারেল ওয়াটার ১.৫ লিটার", "Beverage", "Fresh", "Bottle", 20, 28, 30, True, 60, 240),
    ("Mango Juice 1L", "আমের জুস ১ লিটার", "Beverage", "Pran", "Bottle", 78, 95, 100, True, 24, 180),
    ("Cola 2L", "কোলা ২ লিটার", "Beverage", "Coca-Cola", "Bottle", 75, 92, 95, True, 24, 240),
    ("Tea Leaves 400g", "চা পাতা ৪০০ গ্রাম", "Beverage", "Ispahani", "Packet", 190, 220, 230, True, 15, 400),
    ("Instant Coffee 100g", "ইনস্ট্যান্ট কফি ১০০ গ্রাম", "Beverage", "Nescafe", "Bottle", 295, 340, 350, True, 8, 500),
    ("Potato Chips 50g", "আলুর চিপস ৫০ গ্রাম", "Snacks", "Bombay Sweets", "Packet", 22, 30, 30, True, 50, 150),
    ("Chanachur 200g", "চানাচুর ২০০ গ্রাম", "Snacks", "Bombay Sweets", "Packet", 48, 60, 65, True, 30, 150),
    ("Chocolate Bar 40g", "চকোলেট বার ৪০ গ্রাম", "Snacks", "Cadbury", "Piece", 32, 40, 40, True, 40, 300),
    ("Glucose Biscuit", "গ্লুকোজ বিস্কুট", "Snacks", "Olympic", "Packet", 18, 25, 25, True, 60, 200),
    ("Noodles 8 Pack", "নুডলস ৮ প্যাক", "Snacks", "Maggi", "Packet", 72, 88, 90, True, 25, 240),
    ("Bath Soap 100g", "গোসলের সাবান ১০০ গ্রাম", "Personal Care", "Lux", "Piece", 32, 42, 45, True, 40, None),
    ("Shampoo 200ml", "শ্যাম্পু ২০০ মিলি", "Personal Care", "Sunsilk", "Bottle", 165, 195, 200, True, 15, None),
    ("Toothpaste 150g", "টুথপেস্ট ১৫০ গ্রাম", "Personal Care", "Pepsodent", "Piece", 85, 105, 110, True, 20, None),
    ("Face Wash 100ml", "ফেস ওয়াশ ১০০ মিলি", "Personal Care", "Fair & Lovely", "Piece", 140, 175, 180, True, 10, None),
    ("Detergent Powder 1kg", "ডিটারজেন্ট পাউডার ১ কেজি", "Cleaning", "Wheel", "Packet", 110, 135, 140, True, 25, None),
    ("Dishwash Liquid 500ml", "থালা বাসনের তরল ৫০০ মিলি", "Cleaning", "Vim", "Bottle", 92, 115, 120, True, 15, None),
    ("Floor Cleaner 1L", "ফ্লোর ক্লিনার ১ লিটার", "Cleaning", "Harpic", "Bottle", 140, 170, 175, True, 10, None),
    ("Full Cream Milk 1L", "ফুল ক্রিম দুধ ১ লিটার", "Dairy", "Aarong Dairy", "Packet", 88, 105, 105, False, 40, 14),
    ("Yogurt 500g", "মিষ্টি দই ৫০০ গ্রাম", "Dairy", "Aarong Dairy", "Piece", 95, 120, 120, False, 20, 10),
    ("Butter 200g", "মাখন ২০০ গ্রাম", "Dairy", "Milk Vita", "Piece", 185, 225, 230, False, 10, 90),
    ("Powdered Milk 500g", "গুঁড়া দুধ ৫০০ গ্রাম", "Dairy", "Diploma", "Packet", 420, 485, 495, True, 12, 365),
    ("Frozen Paratha 20pc", "ফ্রোজেন পরোটা ২০ পিস", "Frozen Food", "Kazi Farms", "Packet", 210, 250, 260, True, 15, 120),
    ("Chicken Nuggets 500g", "চিকেন নাগেটস ৫০০ গ্রাম", "Frozen Food", "Kazi Farms", "Packet", 380, 450, 460, True, 8, 90),
    ("Sandwich Bread", "স্যান্ডউইচ ব্রেড", "Bakery", "Pran", "Packet", 48, 60, 60, False, 25, 5),
    ("Cake Rusk 300g", "কেক রাস্ক ৩০০ গ্রাম", "Bakery", "Olympic", "Packet", 55, 70, 70, True, 20, 60),
    ("Ball Pen (Blue)", "বল পেন (নীল)", "Stationery", "Matador", "Piece", 6, 10, 10, True, 100, None),
    ("A4 Paper Ream", "এ৪ কাগজ রিম", "Stationery", "Double A", "Piece", 480, 560, 570, True, 8, None),
    ("Exercise Book 200pg", "খাতা ২০০ পৃষ্ঠা", "Stationery", "Local", "Piece", 48, 65, 70, True, 30, None),
    ("Plastic Bucket 15L", "প্লাস্টিক বালতি ১৫ লিটার", "Household", "RFL", "Piece", 195, 240, 250, True, 6, None),
    ("Mosquito Coil 10pc", "মশার কয়েল ১০ পিস", "Household", "Jet", "Box", 62, 80, 85, True, 30, None),
    ("LED Bulb 9W", "এলইডি বাল্ব ৯ ওয়াট", "Household", "Walton", "Piece", 145, 185, 190, True, 12, None),
    ("Loose Onion (kg)", "পেঁয়াজ (কেজি)", "Grocery", "Local", "Kilogram", 58, 72, 75, False, 30, None),
]

SUPPLIERS = [
    ("Rashid Trading Co.", "Rashid Group", "01711000001", "Md. Rashid", 15),
    ("Pran-RFL Distribution", "PRAN-RFL Group", "01711000002", "Tanvir Alam", 30),
    ("Aarong Dairy Depot", "BRAC Enterprises", "01711000003", "Selina Begum", 7),
    ("Unilever Bangladesh Depot", "Unilever BD", "01711000004", "Habib Rahman", 30),
    ("Dhaka Wholesale Mart", "Dhaka Wholesale", "01711000005", "Shafiq Mia", 0),
    ("Kazi Farms Frozen", "Kazi Farms", "01711000006", "Rubel Hossain", 14),
]

CUSTOMERS = [
    ("Abdul Karim", "01811000001", "RETAIL", 5000, 0), ("Shirin Akter", "01811000002", "VIP", 10000, 5),
    ("Mizanur Rahman", "01811000003", "RETAIL", 3000, 0), ("Rehana Parvin", "01811000004", "RETAIL", 2000, 0),
    ("Bismillah Restaurant", "01811000005", "WHOLESALE", 30000, 3), ("Tania Sultana", "01811000006", "RETAIL", 0, 0),
    ("Golam Mostafa", "01811000007", "RETAIL", 1500, 0), ("Sunrise Tea Stall", "01811000008", "WHOLESALE", 15000, 2),
]

EXPENSES = [("Rent", 18000, "Monthly shop rent"), ("Electricity", 4200, "DESCO bill"), ("Internet", 1500, "Broadband"),
            ("Transport", 1200, "Goods delivery van"), ("Salary", 12000, "Part-time helpers"), ("Maintenance", 2600, "AC service"),
            ("Marketing", 3500, "Facebook ads"), ("Packaging", 1800, "Shopping bags"), ("Other", 900, "Tea & snacks for staff")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete the SQLite database first")
    ap.add_argument("--days", type=int, default=30, help="days of sales history to generate")
    args = ap.parse_args()

    if settings.is_production:
        sys.exit("Refusing to seed demo data in production.")
    if args.reset:
        if not settings.is_sqlite:
            sys.exit("--reset only supports SQLite. Drop and recreate your PostgreSQL database instead.")
        from sqlalchemy.engine import make_url

        db_path = Path(make_url(settings.database_url).database or "")
        for ext in ("", "-wal", "-shm"):
            Path(str(db_path) + ext).unlink(missing_ok=True)

    from app.main import initialise_database

    initialise_database()

    from app.core.database import SessionLocal
    from app.models.auth import Employee, Role, User
    from app.services import auth_service

    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)):
            sys.exit("Database already contains users. Run `python seed.py --reset` (SQLite) to start over.")
        rng = random.Random(2026)
        users = _users(db, auth_service, Role, Employee)
        cat_ids, brand_ids = _catalog(db)
        products = _products(db, users["inventory@example.com"], cat_ids, brand_ids)
        suppliers = _suppliers(db, users["admin@example.com"])
        _purchases(db, rng, users["inventory@example.com"], users["admin@example.com"], products, suppliers)
        customers = _customers(db, users["admin@example.com"])
        _promotions(db, users["admin@example.com"], products)
        _history(db, rng, args.days, users, products, customers, suppliers)
        _expenses(db, rng, users["admin@example.com"], args.days)
        from app.services import notification_service

        notification_service.refresh_alerts(db)
        db.commit()

    print("\nSeed complete.\n")
    print(f"Demo logins (password for all: {DEMO_PASSWORD}) -- CHANGE OR DELETE THESE IN PRODUCTION")
    for email, name, role in USERS:
        print(f"  {email:<28} {role:<18} {name}")


def _users(db, auth_service, Role, Employee):  # noqa: ANN001, ANN202, N803
    out = {}
    for i, (email, name, role_name) in enumerate(USERS, start=1):
        role = db.scalar(select(Role).where(Role.name == role_name))
        user = auth_service.create_user(db, email=email, full_name=name, password=DEMO_PASSWORD, role_ids=[role.id], phone=f"0170000{i:04d}")
        out[email] = user
        db.add(Employee(employee_code=f"EMP-2026-{i:04d}", user_id=user.id, full_name=name, phone=f"0170000{i:04d}", email=email,
                        position=role_name.replace("_", " ").title(), salary=Decimal(str(18000 + i * 2500)), joining_date=date(2025, 1, 1) + timedelta(days=i * 20)))
    db.flush()
    return out


def _catalog(db):  # noqa: ANN001, ANN202
    from app.models.catalog import ProductBrand, ProductCategory

    cats = {}
    for name, bn in CATEGORIES.items():
        c = ProductCategory(name=name, name_bn=bn)
        db.add(c)
        cats[name] = c
    brands = {}
    for b in sorted({p[3] for p in PRODUCTS}):
        row = ProductBrand(name=b)
        db.add(row)
        brands[b] = row
    db.flush()
    return {k: v.id for k, v in cats.items()}, {k: v.id for k, v in brands.items()}


def _products(db, user, cat_ids, brand_ids):  # noqa: ANN001, ANN202
    from app.models.catalog import ProductUnit, TaxRate
    from app.schemas.catalog import ProductCreate
    from app.services import catalog_service

    units = {u.name: u.id for u in db.scalars(select(ProductUnit))}
    vat = db.scalar(select(TaxRate).where(TaxRate.name == "VAT 15%"))
    out = []
    for i, (name, bn, cat, brand, unit, cost, price, mrp, has_vat, reorder, exp_days) in enumerate(PRODUCTS, start=1):
        # shelf prices include VAT: target ~20% margin over cost once the 15% VAT is stripped out
        price = int(round(cost * (1.20 * 1.15 if has_vat else 1.20) / 5.0) * 5) or price
        mrp = price
        data = ProductCreate(
            sku=f"SKU-{i:04d}", name=name, name_bn=bn, category_id=cat_ids[cat], brand_id=brand_ids[brand], unit_id=units[unit],
            purchase_price=Decimal(cost), selling_price=Decimal(price), mrp=Decimal(mrp), tax_rate_id=vat.id if has_vat else None,
            reorder_level=Decimal(reorder), min_stock=Decimal(reorder // 2), track_expiry=exp_days is not None,
            track_batch=exp_days is not None, barcode=f"8941{i:08d}"[:13])
        p = catalog_service.create_product(db, data, user)
        out.append((p, exp_days, cost))
    db.flush()
    return out


def _suppliers(db, user):  # noqa: ANN001, ANN202
    from app.models.purchasing import Supplier
    from app.services import numbering

    rows = []
    for name, company, phone, contact, terms in SUPPLIERS:
        s = Supplier(code=numbering.next_number(db, "SUP", width=4), name=name, company=company, phone=phone, contact_person=contact,
                     payment_terms_days=terms, address="Dhaka, Bangladesh", balance=0, opening_balance=0)
        db.add(s)
        rows.append(s)
    db.flush()
    return rows


def _purchases(db, rng, inv_user, admin, products, suppliers):  # noqa: ANN001, ANN202
    from app.models.finance import PaymentMethod
    from app.schemas.purchasing import PaymentIn, PurchaseCreate, PurchaseItemIn, ReceiveIn, ReceiveItem
    from app.services import payment_service, purchase_service

    by_supplier: dict[int, list] = {}
    for idx, (p, exp_days, cost) in enumerate(products):
        by_supplier.setdefault(idx % len(suppliers), []).append((p, exp_days, cost))
    cash = db.scalar(select(PaymentMethod).where(PaymentMethod.code == "CASH"))
    for si, items in by_supplier.items():
        supplier = suppliers[si]
        po = purchase_service.create_purchase(db, PurchaseCreate(
            supplier_id=supplier.id, submit=True, notes="Initial stock",
            items=[PurchaseItemIn(product_id=p.id, quantity=Decimal(rng.randint(60, 220)), unit_cost=Decimal(cost)) for p, _, cost in items]), inv_user)
        purchase_service.approve(db, po, admin)
        receive_items = []
        for it, (_p, exp_days, _) in zip(po.items, items):
            expiry = None
            if exp_days:
                expiry = date.today() + timedelta(days=rng.randint(max(exp_days // 3, 3), exp_days))
            receive_items.append(ReceiveItem(item_id=it.id, quantity=it.quantity, batch_number=f"LOT-{rng.randint(1000, 9999)}",
                                             manufacturing_date=date.today() - timedelta(days=rng.randint(5, 40)), expiry_date=expiry))
        purchase_service.receive(db, po, ReceiveIn(items=receive_items), inv_user)
        # pay roughly 60% of what we owe so payables are non-zero
        db.flush()
        db.refresh(supplier)
        pay = (supplier.balance * Decimal("0.6")).quantize(Decimal("1"))
        if pay > 0:
            payment_service.pay_supplier(db, supplier, PaymentIn(amount=pay, payment_method_id=cash.id, purchase_id=po.id, notes="Advance payment"), admin)
    # an expiring batch and an already-expired batch so alerts have something to show
    from app.models.inventory import InventoryBatch

    dairy = [p for p, e, _ in products if e and e <= 14]
    if dairy:
        soon = db.scalar(select(InventoryBatch).where(InventoryBatch.product_id == dairy[0].id))
        soon.expiry_date = date.today() + timedelta(days=4)
        gone = db.scalar(select(InventoryBatch).where(InventoryBatch.product_id == dairy[1].id))
        gone.expiry_date = date.today() - timedelta(days=2)
    # a few nearly-out products for the low-stock view
    from app.models.enums import AdjustmentType
    from app.services import inventory_service

    for p, _, _ in products[5:8]:
        db.refresh(p)
        keep = Decimal("3")
        remove = p.current_stock - keep
        if remove > 0:
            inventory_service.adjust_stock(db, p, AdjustmentType.OUT, remove, "Stock count correction (demo)", admin, allow_expired=True) if False else \
                inventory_service.adjust_stock(db, p, AdjustmentType.OUT, remove, "Stock count correction (demo)", admin)
    db.flush()


def _customers(db, user):  # noqa: ANN001, ANN202
    from app.models.customers import Customer
    from app.services import numbering

    rows = []
    for name, phone, ctype, limit, disc in CUSTOMERS:
        c = Customer(code=numbering.next_number(db, "CUS", width=5), name=name, phone=phone, customer_type=ctype, credit_limit=Decimal(limit),
                     discount_percent=Decimal(disc), address="Dhaka", balance=0)
        db.add(c)
        rows.append(c)
    db.flush()
    return rows


def _promotions(db, admin, products):  # noqa: ANN001, ANN202
    from app.models.catalog import ProductCategory
    from app.models.sales import Discount, Promotion

    milk = db.scalar(select(ProductCategory).where(ProductCategory.name == "Dairy"))
    db.add(Promotion(name="Friday Evening Dairy 10% off", promo_type="CATEGORY_PERCENT", category_id=milk.id, value=Decimal("10"),
                     days_of_week="4", start_time="17:00", end_time="21:00"))
    biscuit = next(p for p, _, _ in products if "Glucose" in p.name)
    db.add(Promotion(name="Buy 2 Get 1 Free — Glucose Biscuit", promo_type="BUY_X_GET_Y", product_id=biscuit.id, buy_quantity=Decimal(2), get_quantity=Decimal(1)))
    db.add_all([Discount(name="Staff 10%", code="STAFF10", discount_type="PERCENT", value=Decimal(10), requires_approval=True),
                Discount(name="Loyalty ৳50 off", code="LOYAL50", discount_type="FIXED", value=Decimal(50))])
    db.flush()


def _history(db, rng, days, users, products, customers, suppliers):  # noqa: ANN001, ANN202
    from app.models.customers import CustomerTransaction
    from app.models.finance import CashRegister, CashRegisterSession, CashTransaction, PaymentMethod
    from app.models.inventory import InventoryTransaction
    from app.models.sales import Sale, SalePayment, SaleReturn
    from app.models.system import AuditLog
    from app.schemas.sales import CartItemIn, PaymentLineIn, ReturnItemIn, SaleCreate, SaleReturnCreate
    from app.services import cash_service, sales_service

    methods = {m.code: m for m in db.scalars(select(PaymentMethod))}
    register = db.scalar(select(CashRegister))
    cashiers = [users["cashier@example.com"], users["cashier2@example.com"]]
    sellable = [p for p, _, _ in products]
    for p in sellable:
        db.refresh(p)
    counter = 0

    for back in range(days, 0, -1):
        day = datetime.now(UTC).replace(tzinfo=None, hour=3, minute=0, second=0, microsecond=0) - timedelta(days=back)
        cashier = cashiers[back % 2]
        session = cash_service.open_session(db, cashier, register.id, Decimal("10000"))
        n_sales = rng.randint(6, 16) if day.weekday() != 4 else rng.randint(12, 22)
        stamps = []
        for _ in range(n_sales):
            in_stock = [p for p in sellable if p.current_stock > 8]
            if not in_stock:
                break
            picks = rng.sample(in_stock, k=min(rng.randint(1, 4), len(in_stock)))
            items = []
            for p in picks:
                db.refresh(p)
                q = Decimal(rng.randint(1, 4)) if p.unit.allow_decimal is False else Decimal(str(round(rng.uniform(0.5, 3), 1)))
                items.append(CartItemIn(product_id=p.id, quantity=min(q, p.current_stock)))
            cart = sales_service.build_cart(db, SaleCreate(items=items))[0]
            total = cart.grand_total
            roll = rng.random()
            customer = rng.choice(customers) if rng.random() < 0.35 else None
            payments = [PaymentLineIn(payment_method_id=methods["CASH"].id, amount=total + Decimal(rng.choice([0, 0, 10, 50])))]
            if roll > 0.9:
                payments = [PaymentLineIn(payment_method_id=methods["BKASH"].id, amount=total, transaction_id=f"BK{rng.randint(10**7, 10**8)}")]
            elif roll > 0.8:
                payments = [PaymentLineIn(payment_method_id=methods["CARD"].id, amount=total, reference_number=f"AUTH{rng.randint(1000, 9999)}")]
            elif roll > 0.72 and customer and customer.credit_limit > 0:
                due = min(total * Decimal("0.4"), customer.credit_limit - customer.balance)
                if due > 0:
                    payments = [PaymentLineIn(payment_method_id=methods["CASH"].id, amount=max((total - due).quantize(Decimal("1")), Decimal("1")))]
            try:
                with db.begin_nested():  # a cart that trips a rule (credit limit, stock) is skipped without leaving partial writes
                    sale = sales_service.create_sale(db, SaleCreate(items=items, customer_id=customer.id if customer else None, payments=payments),
                                                     _CreditProxy(cashier))
            except Exception:  # noqa: BLE001 - demo generator only
                continue
            # `day` is 09:00 shop time (03:00 UTC); trading hours run 09:00-21:30
            stamps.append((sale.id, day + timedelta(minutes=rng.randint(0, 750))))
            counter += 1
        # occasional return
        if stamps and rng.random() < 0.4:
            sid = rng.choice(stamps)[0]
            sale = db.get(Sale, sid)
            if sale.total_amount > 0 and sale.due_amount == 0:
                it = sale.items[0]
                try:
                    with db.begin_nested():
                        sales_service.create_return(db, SaleReturnCreate(sale_id=sale.id, reason="Customer returned item (demo)", refund_method_id=methods["CASH"].id,
                                                                           items=[ReturnItemIn(sale_item_id=it.id, quantity=Decimal(1))]), cashier)
                except Exception:  # noqa: BLE001
                    pass
        exp = cash_service.expected_cash(db, session.id)
        diff = Decimal(rng.choice([0, 0, 0, 0, -20, 10, -100])) if back % 6 else Decimal(-250)
        cash_service.close_session(db, session, cashier, exp + diff, "Counting difference (demo)" if diff else None)
        db.flush()
        # backdate everything created for this day so charts show a realistic history
        for sid, when in stamps:
            db.execute(update(Sale).where(Sale.id == sid).values(sale_date=when, created_at=when))
            db.execute(update(SalePayment).where(SalePayment.sale_id == sid).values(created_at=when))
            db.execute(update(InventoryTransaction).where(InventoryTransaction.reference_type == "sale", InventoryTransaction.reference_id == sid).values(created_at=when))
            db.execute(update(CustomerTransaction).where(CustomerTransaction.reference_type == "sale", CustomerTransaction.reference_id == sid).values(created_at=when))
        close_at = day + timedelta(hours=12)
        db.execute(update(CashRegisterSession).where(CashRegisterSession.id == session.id).values(opened_at=day, closed_at=close_at))
        db.execute(update(CashTransaction).where(CashTransaction.session_id == session.id).values(created_at=day + timedelta(hours=1)))
        for r in db.scalars(select(SaleReturn).where(SaleReturn.session_id == session.id)):
            r.created_at = close_at - timedelta(hours=1)
            db.execute(update(InventoryTransaction).where(InventoryTransaction.reference_type == "sale_return", InventoryTransaction.reference_id == r.id).values(created_at=r.created_at))
        db.execute(update(AuditLog).where(AuditLog.entity == "cash_session", AuditLog.entity_id == str(session.id)).values(created_at=close_at))
    print(f"Generated {counter} historical sales over {days} days.")


class _CreditProxy:
    """Wraps a user so seed-generated credit sales pass the sale.credit check without altering roles in the database."""

    def __init__(self, user) -> None:  # noqa: ANN001
        self._user = user

    def __getattr__(self, item: str):  # noqa: ANN204
        return getattr(self._user, item)

    @property
    def permission_codes(self) -> set[str]:
        return self._user.permission_codes | {"sale.credit"}


def _expenses(db, rng, admin, days):  # noqa: ANN001, ANN202
    from app.models.finance import Expense, ExpenseCategory, PaymentMethod
    from app.services import numbering

    cash = db.scalar(select(PaymentMethod).where(PaymentMethod.code == "CASH"))
    cats = {c.name: c.id for c in db.scalars(select(ExpenseCategory))}
    today = date.today()
    for i, (cat, amount, desc) in enumerate(EXPENSES):
        d = today - timedelta(days=min(i * 3 + 1, days - 1))
        db.add(Expense(expense_number=numbering.next_number(db, "EXP"), category_id=cats[cat], amount=Decimal(amount), description=desc,
                       expense_date=d, payment_method_id=cash.id, created_by=admin.id))
    db.flush()


if __name__ == "__main__":
    main()
