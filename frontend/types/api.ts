// Shapes returned by the FastAPI backend. Money and quantities arrive as JSON numbers.

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface User {
  id: number
  email: string
  full_name: string
  phone: string | null
  is_active: boolean
  language: string
  totp_enabled: boolean
  must_change_password: boolean
  last_login_at: string | null
  max_discount_percent: number | null
  role_names: string[]
}

export interface Me extends User {
  permissions: string[]
  landing_path: string
}

export interface Role {
  id: number
  name: string
  description: string
  is_system: boolean
  permissions: string[]
}

export interface PermissionDef {
  code: string
  module: string
  description: string
}

export interface Category { id: number; name: string; name_bn: string | null; parent_id: number | null; is_active: boolean }
export interface Brand { id: number; name: string; is_active: boolean }
export interface Unit { id: number; name: string; short_name: string; allow_decimal: boolean; is_active: boolean }
export interface TaxRate { id: number; name: string; rate: number; effective_from: string | null; effective_to: string | null; is_active: boolean; is_default: boolean }
export interface PaymentMethod { id: number; code: string; name: string; method_type: string; requires_reference: boolean; is_active: boolean; sort_order: number }

export interface Barcode { id: number; barcode: string; format: string; is_primary: boolean }

export interface Product {
  id: number
  sku: string
  barcode: string | null
  barcodes: Barcode[]
  name: string
  name_bn: string | null
  description: string | null
  category: { id: number; name: string } | null
  subcategory: { id: number; name: string } | null
  brand: { id: number; name: string } | null
  unit: { id: number; name: string; short_name: string; allow_decimal: boolean }
  purchase_price: number | null
  selling_price: number
  mrp: number | null
  tax_rate: { id: number; name: string; rate: number } | null
  discount_percent: number
  min_stock: number
  max_stock: number | null
  reorder_level: number
  supplier_id: number | null
  image_path: string | null
  track_expiry: boolean
  track_batch: boolean
  is_active: boolean
  current_stock: number
  created_at: string
}

export interface ProductLookup {
  id: number
  sku: string
  barcode: string | null
  name: string
  name_bn: string | null
  unit: string
  allow_decimal: boolean
  selling_price: number
  mrp: number | null
  tax_rate: number
  discount_percent: number
  current_stock: number
  category_id: number | null
  image_path: string | null
  track_expiry: boolean
}

export interface StockRow {
  product_id: number
  sku: string
  barcode: string | null
  name: string
  category: string | null
  unit: string
  current_stock: number
  reserved_stock: number
  available_stock: number
  damaged_stock: number
  expired_stock: number
  reorder_level: number
  stock_value: number | null
  status: "out" | "low" | "ok"
}

export interface Batch {
  id: number
  product_id: number
  product_name: string
  sku: string
  batch_number: string
  manufacturing_date: string | null
  expiry_date: string | null
  days_to_expiry: number | null
  purchase_cost: number | null
  quantity_received: number
  quantity_remaining: number
  stock_value: number | null
  received_at: string
}

export interface Movement {
  id: number
  created_at: string
  product_id: number
  product_name: string
  sku: string
  batch_id: number | null
  batch_number: string | null
  txn_type: string
  quantity: number
  balance_after: number
  unit_cost: number | null
  reference_type: string | null
  reference_id: number | null
  reason: string | null
  user_name: string | null
}

export interface Adjustment {
  id: number
  adjustment_number: string
  product_id: number
  product_name: string | null
  adjustment_type: string
  quantity: number
  reason: string
  created_at: string
  user_name: string | null
}

export interface InventorySummary {
  stock_value: number | null
  total_units: number
  product_count: number
  low_stock_count: number
  out_of_stock_count: number
  expiring_soon_count: number
  expired_count: number
  healthy_count: number
}

export interface Supplier {
  id: number
  code: string
  name: string
  company: string | null
  phone: string | null
  email: string | null
  address: string | null
  contact_person: string | null
  tax_id: string | null
  opening_balance: number
  balance: number
  payment_terms_days: number
  notes: string | null
  is_active: boolean
  created_at: string
}

export interface SupplierProfile extends Supplier {
  total_purchases: number
  total_paid: number
  total_returns: number
  purchase_count: number
}

export interface LedgerRow {
  id: number
  created_at: string
  txn_type: string
  amount: number
  balance_after: number
  reference_type: string | null
  reference_id: number | null
  reference_number: string | null
  notes: string | null
  user_name: string | null
}

export interface PurchaseItem {
  id: number
  product_id: number
  product_name: string | null
  sku: string | null
  track_expiry: boolean
  quantity: number
  received_quantity: number
  returned_quantity: number
  unit_cost: number
  discount_amount: number
  tax_rate: number
  tax_amount: number
  line_total: number
  received_value: number
}

export interface Purchase {
  id: number
  po_number: string
  supplier_id: number
  supplier_name: string | null
  status: string
  order_date: string
  expected_date: string | null
  subtotal: number
  discount_amount: number
  tax_amount: number
  total_amount: number
  received_value: number
  paid_amount: number
  notes: string | null
  cancelled_reason: string | null
  created_at: string
  approved_at: string | null
  items: PurchaseItem[]
}

export interface PurchaseReturn {
  id: number
  return_number: string
  supplier_id: number
  supplier_name: string | null
  purchase_id: number | null
  return_date: string
  total_amount: number
  reason: string
  created_at: string
  items: { id: number; product_id: number; product_name: string | null; batch_id: number | null; quantity: number; unit_cost: number; amount: number }[]
}

export interface GoodsReceipt {
  id: number
  grn_number: string
  purchase_id: number
  po_number: string | null
  supplier_name: string | null
  value: number
  received_at: string
  received_by_name: string | null
  notes: string | null
}

export interface Customer {
  id: number
  code: string
  name: string
  phone: string | null
  email: string | null
  address: string | null
  customer_type: string
  loyalty_points: number
  discount_percent: number
  opening_balance: number
  balance: number
  credit_limit: number
  is_active: boolean
  created_at: string
}

export interface CustomerProfile extends Customer {
  total_purchases: number
  total_returns: number
  total_paid: number
  sale_count: number
  last_purchase_at: string | null
}

export interface PreviewLine {
  product_id: number
  name: string
  quantity: number
  unit_price: number
  gross: number
  auto_discount: number
  promotion: string | null
  manual_discount: number
  invoice_discount: number
  discount: number
  tax_rate: number
  tax_amount: number
  line_total: number
  stock_available: number
}

export interface CartPreview {
  lines: PreviewLine[]
  subtotal: number
  discount_total: number
  manual_discount_percent: number
  tax_total: number
  grand_total: number
  discount_allowed: boolean
  max_discount_percent: number
  customer_balance: number | null
  credit_available: number | null
}

export interface SaleItem {
  id: number
  product_id: number
  product_name: string
  sku: string
  quantity: number
  returned_quantity: number
  unit_price: number
  discount_amount: number
  tax_rate: number
  tax_amount: number
  line_total: number
  returned_amount: number
  cogs_amount: number | null
}

export interface SalePayment {
  id: number
  payment_method_id: number
  method_name: string | null
  method_type: string | null
  amount: number
  reference_number: string | null
  transaction_id: string | null
}

export interface Sale {
  id: number
  invoice_number: string
  sale_date: string
  status: string
  return_status: string
  customer_id: number | null
  customer_name: string | null
  customer_phone: string | null
  cashier_id: number
  cashier_name: string | null
  subtotal: number
  discount_amount: number
  tax_amount: number
  total_amount: number
  paid_amount: number
  due_amount: number
  tendered_amount: number
  change_amount: number
  returned_amount: number
  cogs_amount: number | null
  notes: string | null
  void_reason: string | null
  items: SaleItem[]
  payments: SalePayment[]
}

export interface SaleReturn {
  id: number
  return_number: string
  sale_id: number
  invoice_number: string | null
  customer_id: number | null
  total_amount: number
  due_reduced: number
  refunded_amount: number
  refund_method_name: string | null
  reason: string
  created_at: string
  items: { id: number; sale_item_id: number; product_id: number; product_name: string | null; quantity: number; amount: number }[]
}

export interface Register { id: number; name: string; location: string | null; is_active: boolean }

export interface CashSession {
  id: number
  register_id: number
  register_name: string
  opened_by: number
  opened_by_name: string
  opened_at: string
  closed_at: string | null
  opening_cash: number
  expected_cash: number
  actual_cash: number | null
  difference: number | null
  discrepancy_reason: string | null
  status: string
  breakdown: Record<string, number>
}

export interface Promotion {
  id: number
  name: string
  promo_type: string
  product_id: number | null
  category_id: number | null
  buy_quantity: number
  get_quantity: number
  value: number
  start_at: string | null
  end_at: string | null
  days_of_week: string | null
  start_time: string | null
  end_time: string | null
  priority: number
  is_active: boolean
}

export interface Discount { id: number; name: string; code: string | null; discount_type: string; value: number; requires_approval: boolean; is_active: boolean }

export interface ExpenseCategory { id: number; name: string; is_active: boolean }

export interface Expense {
  id: number
  expense_number: string
  category_id: number
  category_name: string | null
  amount: number
  description: string | null
  expense_date: string
  payment_method_id: number
  payment_method_name: string | null
  employee_id: number | null
  has_attachment: boolean
  status: string
  void_reason: string | null
  created_at: string
  created_by_name: string | null
}

export interface Employee {
  id: number
  employee_code: string
  full_name: string
  phone: string | null
  email: string | null
  address: string | null
  position: string | null
  joining_date: string | null
  status: string
  user_id: number | null
  user_email: string | null
  salary: number | null
  national_id: string | null
}

export interface Notification {
  id: number
  type: string
  severity: string
  title: string
  message: string
  entity: string | null
  entity_id: string | null
  created_at: string
  is_read: boolean
}

export interface AuditLog {
  id: number
  created_at: string
  user_id: number | null
  user_email: string | null
  action: string
  entity: string
  entity_id: string | null
  description: string | null
  old_value: unknown
  new_value: unknown
  ip_address: string | null
}

export interface Dashboard {
  period: { start: string; end: string; granularity: string }
  kpis: {
    sales_total: number
    invoices: number
    returns_total: number
    discounts: number
    profit: number | null
    net_profit: number | null
    expenses: number | null
    purchases: number | null
    stock_value: number | null
    low_stock: number | null
    out_of_stock: number | null
    expiring_soon: number | null
    expired: number | null
    supplier_payables: number | null
    customer_receivables: number | null
  }
  series: { bucket: string; sales: number; revenue?: number; cogs?: number; profit?: number; invoices: number }[]
  top_products: { product_id: number; name: string; quantity: number; amount: number }[]
  category_sales: { category: string; amount: number }[]
  inventory_status: { status: string; count: number }[] | null
  recent: { type: string; id: number; number: string; party: string; amount: number; status: string; at: string }[]
  unread_notifications: number
}

export interface ReportColumn { key: string; label: string; type: "text" | "int" | "money" | "qty" | "percent" | "date" }

export interface ReportData {
  title: string
  columns: ReportColumn[]
  rows: Record<string, string | number | null>[]
  summary: Record<string, number | string>
  period: { start: string; end: string } | null
}

export type Settings = Record<string, string | number | boolean | null>

export interface BackupFile { name: string; size: number; created_at: string }

export interface ImportResult {
  total_rows: number
  valid_rows: number
  imported: number
  errors: { row: number; message: string; value: string }[]
  error_count: number
  committed: boolean
  dry_run: boolean
}

export interface DiscountRequest {
  id: number
  status: "PENDING" | "APPROVED" | "REJECTED" | "USED" | "EXPIRED"
  discount_percent: number
  discount_amount: number
  reason: string
  requested_by: number
  requested_by_name: string | null
  decided_by: number | null
  decided_by_name: string | null
  decided_at: string | null
  decision_note: string | null
  expires_at: string
  used_sale_id: number | null
  created_at: string
}
