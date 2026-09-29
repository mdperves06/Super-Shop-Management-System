from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover
        return self.value


class InventoryTxnType(StrEnum):
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    SALE_RETURN = "SALE_RETURN"
    PURCHASE_RETURN = "PURCHASE_RETURN"
    ADJUSTMENT_IN = "ADJUSTMENT_IN"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT"
    DAMAGE = "DAMAGE"
    EXPIRED = "EXPIRED"
    TRANSFER = "TRANSFER"  # reserved for multi-branch deployments
    SALE_VOID = "SALE_VOID"


class PurchaseStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class SaleStatus(StrEnum):
    COMPLETED = "COMPLETED"
    VOIDED = "VOIDED"


class ReturnStatus(StrEnum):
    NONE = "NONE"
    PARTIAL = "PARTIAL"
    FULL = "FULL"


class LedgerType(StrEnum):
    OPENING = "OPENING"
    SALE = "SALE"
    PURCHASE = "PURCHASE"
    PAYMENT = "PAYMENT"
    RETURN = "RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    VOID = "VOID"


class PaymentMethodType(StrEnum):
    CASH = "CASH"
    CARD = "CARD"
    MOBILE = "MOBILE"
    BANK = "BANK"
    OTHER = "OTHER"


class CashTxnType(StrEnum):
    OPENING = "OPENING"
    SALE = "SALE"
    REFUND = "REFUND"
    EXPENSE = "EXPENSE"
    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"
    CUSTOMER_PAYMENT = "CUSTOMER_PAYMENT"
    SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT"
    SALE_VOID = "SALE_VOID"


class PromotionType(StrEnum):
    BUY_X_GET_Y = "BUY_X_GET_Y"
    PERCENT_OFF = "PERCENT_OFF"
    FIXED_OFF = "FIXED_OFF"
    CATEGORY_PERCENT = "CATEGORY_PERCENT"


class AdjustmentType(StrEnum):
    IN = "IN"
    OUT = "OUT"
    DAMAGE = "DAMAGE"
    EXPIRED = "EXPIRED"
