"""Permission catalogue and default role definitions (single source of truth)."""

PERMISSIONS: dict[str, dict[str, str]] = {
    "dashboard": {
        "dashboard.view": "View the dashboard",
        "dashboard.finance": "View profit, purchases and payables on the dashboard",
    },
    "product": {
        "product.read": "View products",
        "product.create": "Create products",
        "product.update": "Edit products",
        "product.delete": "Delete (archive) products",
        "product.cost": "View and change purchase cost",
        "product.import": "Import products from CSV",
        "category.manage": "Manage categories, brands and units",
    },
    "inventory": {
        "inventory.read": "View stock, batches and movements",
        "inventory.adjust": "Adjust stock (damage, expiry, corrections)",
    },
    "supplier": {
        "supplier.read": "View suppliers and ledgers",
        "supplier.create": "Create suppliers",
        "supplier.update": "Edit suppliers",
        "supplier.delete": "Delete (archive) suppliers",
        "supplier.payment": "Record supplier payments",
    },
    "purchase": {
        "purchase.read": "View purchases",
        "purchase.create": "Create and edit purchase orders",
        "purchase.approve": "Approve purchase orders",
        "purchase.receive": "Receive stock against purchases",
        "purchase.cancel": "Cancel purchase orders",
        "purchase.return": "Return goods to suppliers",
    },
    "sale": {
        "sale.create": "Use the POS and create sales",
        "sale.read": "View sales and invoices",
        "sale.read_all": "View sales of all cashiers",
        "sale.cancel": "Void sales",
        "sale.return": "Process sale returns",
        "sale.credit": "Sell on credit",
        "discount.override": "Give discounts above the cashier limit",
        "discount.approve": "Approve or reject cashiers' discount requests",
        "promotion.manage": "Manage promotions and discount presets",
    },
    "register": {
        "register.use": "Open and close own cash register session",
        "register.manage": "View all register sessions and manage registers",
    },
    "customer": {
        "customer.read": "View customers and ledgers",
        "customer.create": "Create customers",
        "customer.update": "Edit customers",
        "customer.delete": "Delete (archive) customers",
        "customer.payment": "Record customer payments",
        "customer.import": "Import customers from CSV",
    },
    "employee": {
        "employee.read": "View employees",
        "employee.create": "Create employees",
        "employee.update": "Edit employees",
        "employee.delete": "Delete (archive) employees",
        "employee.salary": "View and edit salary information",
    },
    "expense": {
        "expense.read": "View expenses",
        "expense.create": "Record expenses",
        "expense.update": "Edit expenses",
        "expense.delete": "Void expenses",
    },
    "report": {
        "report.sales": "Sales reports",
        "report.inventory": "Inventory reports",
        "report.purchases": "Purchase reports",
        "report.expenses": "Expense reports",
        "report.profit": "Profit reports",
        "report.finance": "Financial reports (cash flow, payables, receivables)",
        "report.export": "Export reports and data",
    },
    "system": {
        "notification.read": "View notifications",
        "audit.read": "View audit logs",
        "settings.read": "View settings",
        "settings.update": "Change settings",
        "user.read": "View users",
        "user.create": "Create users",
        "user.update": "Edit users",
        "user.delete": "Deactivate users",
        "role.manage": "Manage roles and permissions",
        "backup.manage": "Create/download/restore backups",
        "import.manage": "Import/export bulk data",
    },
}

ALL_PERMISSIONS = [code for group in PERMISSIONS.values() for code in group]


def _pick(*prefixes: str, exclude: tuple[str, ...] = ()) -> list[str]:
    out = []
    for code in ALL_PERMISSIONS:
        if code in exclude:
            continue
        if any(code == p or code.startswith(p) for p in prefixes):
            out.append(code)
    return out


SUPER_ADMIN = "SUPER_ADMIN"
ADMIN = "ADMIN"
MANAGER = "MANAGER"
CASHIER = "CASHIER"
INVENTORY_MANAGER = "INVENTORY_MANAGER"
ACCOUNTANT = "ACCOUNTANT"
STAFF = "STAFF"

_ADMIN_EXCLUDED = ("backup.manage", "role.manage")

DEFAULT_ROLES: dict[str, dict] = {
    SUPER_ADMIN: {
        "description": "Full access to everything including backups, roles and system configuration.",
        "permissions": ALL_PERMISSIONS,
    },
    ADMIN: {
        "description": "Owner / business administrator. Everything except backup/restore and role management.",
        "permissions": [p for p in ALL_PERMISSIONS if p not in _ADMIN_EXCLUDED],
    },
    MANAGER: {
        "description": "Day-to-day management of catalogue, stock, purchasing, customers, staff and reports.",
        "permissions": _pick(
            "dashboard.", "product.", "category.", "inventory.", "supplier.", "purchase.", "sale.", "discount.",
            "promotion.", "register.", "customer.", "employee.read", "expense.", "report.", "notification.",
            "settings.read",
            exclude=("supplier.delete", "customer.delete", "product.import"),
        )
        + ["product.import", "customer.import"],
    },
    CASHIER: {
        "description": "POS operator: register, sales, payments, receipts and approved returns.",
        "permissions": [
            "dashboard.view", "product.read", "inventory.read", "sale.create", "sale.read", "sale.return",
            "register.use", "customer.read", "customer.create", "customer.payment", "notification.read",
        ],
    },
    INVENTORY_MANAGER: {
        "description": "Receives stock, adjusts inventory, tracks batches and expiry.",
        "permissions": [
            "dashboard.view", "product.read", "product.create", "product.update", "category.manage",
            "inventory.read", "inventory.adjust", "supplier.read", "purchase.read", "purchase.receive",
            "purchase.return", "report.inventory", "report.purchases", "notification.read",
        ],
    },
    ACCOUNTANT: {
        "description": "Read access to sales, purchases, expenses, payments and financial reports.",
        "permissions": [
            "dashboard.view", "dashboard.finance", "sale.read", "sale.read_all", "purchase.read", "supplier.read",
            "supplier.payment", "customer.read", "customer.payment", "expense.read", "expense.create",
            "expense.update", "report.sales", "report.purchases", "report.expenses", "report.profit",
            "report.finance", "report.inventory", "report.export", "product.read", "product.cost",
            "inventory.read", "register.manage", "notification.read",
        ],
    },
    STAFF: {
        "description": "Limited read-only access.",
        "permissions": ["dashboard.view", "product.read", "inventory.read", "notification.read"],
    },
}
