"""Import every model module so Base.metadata is complete (Alembic, tests, create_all)."""

from app.models.auth import (  # noqa: F401
    Attendance,
    Employee,
    PasswordResetToken,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.models.catalog import (  # noqa: F401
    Product,
    ProductBarcode,
    ProductBrand,
    ProductCategory,
    ProductUnit,
    TaxRate,
)
from app.models.customers import Customer, CustomerAddress, CustomerTransaction  # noqa: F401
from app.models.finance import (  # noqa: F401
    CashRegister,
    CashRegisterSession,
    CashTransaction,
    Expense,
    ExpenseCategory,
    Payment,
    PaymentMethod,
)
from app.models.inventory import Inventory, InventoryBatch, InventoryTransaction, StockAdjustment  # noqa: F401
from app.models.purchasing import (  # noqa: F401
    GoodsReceipt,
    PurchaseItem,
    PurchaseOrder,
    PurchaseReturn,
    PurchaseReturnItem,
    Supplier,
    SupplierProduct,
    SupplierTransaction,
)
from app.models.sales import (  # noqa: F401
    Discount,
    DiscountRequest,
    Promotion,
    Sale,
    SaleItem,
    SaleItemAllocation,
    SalePayment,
    SaleReturn,
    SaleReturnItem,
)
from app.models.system import (  # noqa: F401
    AuditLog,
    Notification,
    NotificationRead,
    NumberSequence,
    Setting,
    UploadedFile,
)
