# Database schema

_Generated from the SQLAlchemy models by `backend/scripts/gen_docs.py`._

51 tables. Migrations live in `backend/alembic/versions`. Money is `NUMERIC(14,2)`, quantities `NUMERIC(14,3)`, all timestamps are stored as UTC.

Financial records are never physically deleted: sales are voided, expenses voided, products/suppliers/customers/employees soft-deleted.

## `attendance`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `employee_id` | INTEGER | no | FK → `employees.id`, indexed |
| `work_date` | DATE | no |  |
| `check_in` | DATETIME | yes |  |
| `check_out` | DATETIME | yes |  |
| `status` | VARCHAR(20) | no |  |
| `note` | VARCHAR(255) | yes |  |

Constraints: unique(employee_id, work_date)

## `audit_logs`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `user_id` | INTEGER | yes | FK → `users.id`, indexed |
| `user_email` | VARCHAR(255) | yes |  |
| `action` | VARCHAR(80) | no | indexed |
| `entity` | VARCHAR(60) | no |  |
| `entity_id` | VARCHAR(60) | yes |  |
| `description` | TEXT | yes |  |
| `old_value` | JSON | yes |  |
| `new_value` | JSON | yes |  |
| `ip_address` | VARCHAR(64) | yes |  |
| `user_agent` | VARCHAR(255) | yes |  |
| `created_at` | DATETIME | no | indexed |

## `cash_register_sessions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `register_id` | INTEGER | no | FK → `cash_registers.id`, indexed |
| `opened_by` | INTEGER | no | FK → `users.id`, indexed |
| `opened_at` | DATETIME | no |  |
| `opening_cash` | NUMERIC(14, 2) | no |  |
| `closed_by` | INTEGER | yes | FK → `users.id` |
| `closed_at` | DATETIME | yes |  |
| `expected_cash` | NUMERIC(14, 2) | yes |  |
| `actual_cash` | NUMERIC(14, 2) | yes |  |
| `difference` | NUMERIC(14, 2) | yes |  |
| `discrepancy_reason` | TEXT | yes |  |
| `status` | VARCHAR(10) | no | indexed |

## `cash_registers`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `name` | VARCHAR(80) | no | unique |
| `location` | VARCHAR(120) | yes |  |
| `is_active` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `cash_transactions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `session_id` | INTEGER | no | FK → `cash_register_sessions.id`, indexed |
| `txn_type` | VARCHAR(20) | no |  |
| `amount` | NUMERIC(14, 2) | no |  |
| `reference_type` | VARCHAR(30) | yes |  |
| `reference_id` | INTEGER | yes |  |
| `note` | VARCHAR(255) | yes |  |
| `user_id` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no |  |

## `customer_addresses`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `customer_id` | INTEGER | no | FK → `customers.id`, indexed |
| `label` | VARCHAR(50) | no |  |
| `address` | TEXT | no |  |
| `is_default` | BOOLEAN | no |  |

## `customer_transactions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `customer_id` | INTEGER | no | FK → `customers.id` |
| `txn_type` | VARCHAR(20) | no |  |
| `amount` | NUMERIC(14, 2) | no |  |
| `balance_after` | NUMERIC(14, 2) | no |  |
| `reference_type` | VARCHAR(30) | yes |  |
| `reference_id` | INTEGER | yes |  |
| `reference_number` | VARCHAR(40) | yes |  |
| `notes` | TEXT | yes |  |
| `user_id` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no | indexed |

## `customers`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `code` | VARCHAR(30) | no | unique |
| `name` | VARCHAR(150) | no | indexed |
| `phone` | VARCHAR(30) | yes | unique, indexed |
| `email` | VARCHAR(255) | yes |  |
| `address` | TEXT | yes |  |
| `customer_type` | VARCHAR(20) | no |  |
| `loyalty_points` | INTEGER | no |  |
| `discount_percent` | NUMERIC(6, 2) | no |  |
| `opening_balance` | NUMERIC(14, 2) | no |  |
| `balance` | NUMERIC(14, 2) | no |  |
| `credit_limit` | NUMERIC(14, 2) | no |  |
| `is_active` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `is_deleted` | BOOLEAN | no | indexed |
| `deleted_at` | DATETIME | yes |  |

## `discounts`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `name` | VARCHAR(100) | no |  |
| `code` | VARCHAR(30) | yes | unique |
| `discount_type` | VARCHAR(10) | no |  |
| `value` | NUMERIC(14, 2) | no |  |
| `requires_approval` | BOOLEAN | no |  |
| `is_active` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `employees`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `employee_code` | VARCHAR(30) | no | unique, indexed |
| `user_id` | INTEGER | yes | FK → `users.id` |
| `full_name` | VARCHAR(150) | no | indexed |
| `phone` | VARCHAR(30) | yes |  |
| `email` | VARCHAR(255) | yes |  |
| `address` | TEXT | yes |  |
| `position` | VARCHAR(100) | yes |  |
| `salary` | NUMERIC(14, 2) | no |  |
| `joining_date` | DATE | yes |  |
| `status` | VARCHAR(20) | no |  |
| `national_id` | VARCHAR(50) | yes |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `is_deleted` | BOOLEAN | no | indexed |
| `deleted_at` | DATETIME | yes |  |

## `expense_categories`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `name` | VARCHAR(80) | no | unique |
| `is_active` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `expenses`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `expense_number` | VARCHAR(30) | no | unique |
| `category_id` | INTEGER | no | FK → `expense_categories.id`, indexed |
| `amount` | NUMERIC(14, 2) | no |  |
| `description` | TEXT | yes |  |
| `expense_date` | DATE | no | indexed |
| `payment_method_id` | INTEGER | no | FK → `payment_methods.id` |
| `employee_id` | INTEGER | yes | FK → `employees.id` |
| `attachment_path` | VARCHAR(255) | yes |  |
| `status` | VARCHAR(10) | no |  |
| `void_reason` | TEXT | yes |  |
| `created_by` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `is_deleted` | BOOLEAN | no | indexed |
| `deleted_at` | DATETIME | yes |  |

## `goods_receipts`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `grn_number` | VARCHAR(30) | no | unique |
| `purchase_id` | INTEGER | no | FK → `purchase_orders.id`, indexed |
| `received_by` | INTEGER | yes | FK → `users.id` |
| `received_at` | DATETIME | no |  |
| `value` | NUMERIC(14, 2) | no |  |
| `notes` | TEXT | yes |  |

## `inventory`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `product_id` | INTEGER | no | FK → `products.id`, unique |
| `current_stock` | NUMERIC(14, 3) | no |  |
| `reserved_stock` | NUMERIC(14, 3) | no |  |
| `damaged_stock` | NUMERIC(14, 3) | no |  |
| `expired_stock` | NUMERIC(14, 3) | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `inventory_batches`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `product_id` | INTEGER | no | FK → `products.id`, indexed |
| `batch_number` | VARCHAR(60) | no | indexed |
| `manufacturing_date` | DATE | yes |  |
| `expiry_date` | DATE | yes | indexed |
| `purchase_cost` | NUMERIC(14, 2) | no |  |
| `quantity_received` | NUMERIC(14, 3) | no |  |
| `quantity_remaining` | NUMERIC(14, 3) | no |  |
| `supplier_id` | INTEGER | yes | FK → `suppliers.id` |
| `goods_receipt_id` | INTEGER | yes | FK → `goods_receipts.id` |
| `received_at` | DATETIME | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints: check `quantity_remaining >= 0 OR quantity_remaining IS NULL`

## `inventory_transactions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `product_id` | INTEGER | no | FK → `products.id` |
| `batch_id` | INTEGER | yes | FK → `inventory_batches.id` |
| `txn_type` | VARCHAR(30) | no | indexed |
| `quantity` | NUMERIC(14, 3) | no |  |
| `balance_after` | NUMERIC(14, 3) | no |  |
| `unit_cost` | NUMERIC(14, 2) | no |  |
| `reference_type` | VARCHAR(30) | yes |  |
| `reference_id` | INTEGER | yes |  |
| `reason` | TEXT | yes |  |
| `user_id` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no | indexed |

## `notification_reads`

| Column | Type | Null | Notes |
|---|---|---|---|
| `notification_id` | INTEGER | no | PK, FK → `notifications.id` |
| `user_id` | INTEGER | no | PK, FK → `users.id` |
| `read_at` | DATETIME | no |  |

## `notifications`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `type` | VARCHAR(50) | no | indexed |
| `severity` | VARCHAR(20) | no |  |
| `title` | VARCHAR(200) | no |  |
| `message` | TEXT | no |  |
| `entity` | VARCHAR(60) | yes |  |
| `entity_id` | VARCHAR(60) | yes |  |
| `required_permission` | VARCHAR(80) | yes |  |
| `dedupe_key` | VARCHAR(160) | yes | unique |
| `created_at` | DATETIME | no | indexed |

## `number_sequences`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `prefix` | VARCHAR(20) | no |  |
| `year` | INTEGER | no |  |
| `last_value` | INTEGER | no |  |

Constraints: unique(prefix, year)

## `password_reset_tokens`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `user_id` | INTEGER | no | FK → `users.id`, indexed |
| `token_hash` | VARCHAR(64) | no | unique |
| `expires_at` | DATETIME | no |  |
| `used_at` | DATETIME | yes |  |
| `created_at` | DATETIME | no |  |

## `payment_methods`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `code` | VARCHAR(30) | no | unique |
| `name` | VARCHAR(80) | no |  |
| `method_type` | VARCHAR(15) | no |  |
| `requires_reference` | BOOLEAN | no |  |
| `is_active` | BOOLEAN | no |  |
| `sort_order` | INTEGER | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `payments`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `payment_number` | VARCHAR(30) | no | unique |
| `direction` | VARCHAR(3) | no |  |
| `party_type` | VARCHAR(15) | no |  |
| `party_id` | INTEGER | no |  |
| `payment_method_id` | INTEGER | no | FK → `payment_methods.id` |
| `amount` | NUMERIC(14, 2) | no |  |
| `reference_number` | VARCHAR(80) | yes |  |
| `transaction_id` | VARCHAR(80) | yes |  |
| `purchase_id` | INTEGER | yes | FK → `purchase_orders.id` |
| `notes` | TEXT | yes |  |
| `user_id` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no | indexed |

## `permissions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `code` | VARCHAR(80) | no | unique, indexed |
| `module` | VARCHAR(50) | no | indexed |
| `description` | VARCHAR(255) | no |  |

## `product_barcodes`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `product_id` | INTEGER | no | FK → `products.id`, indexed |
| `barcode` | VARCHAR(64) | no | unique, indexed |
| `format` | VARCHAR(20) | no |  |
| `is_primary` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `product_brands`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `name` | VARCHAR(100) | no | unique |
| `is_active` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `is_deleted` | BOOLEAN | no | indexed |
| `deleted_at` | DATETIME | yes |  |

## `product_categories`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `name` | VARCHAR(100) | no | indexed |
| `name_bn` | VARCHAR(100) | yes |  |
| `parent_id` | INTEGER | yes | FK → `product_categories.id` |
| `is_active` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `is_deleted` | BOOLEAN | no | indexed |
| `deleted_at` | DATETIME | yes |  |

Constraints: unique(name, parent_id)

## `product_units`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `name` | VARCHAR(50) | no | unique |
| `short_name` | VARCHAR(15) | no |  |
| `allow_decimal` | BOOLEAN | no |  |
| `is_active` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `products`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `sku` | VARCHAR(60) | no | unique, indexed |
| `name` | VARCHAR(200) | no |  |
| `name_bn` | VARCHAR(200) | yes |  |
| `description` | TEXT | yes |  |
| `category_id` | INTEGER | yes | FK → `product_categories.id`, indexed |
| `subcategory_id` | INTEGER | yes | FK → `product_categories.id` |
| `brand_id` | INTEGER | yes | FK → `product_brands.id` |
| `unit_id` | INTEGER | no | FK → `product_units.id` |
| `purchase_price` | NUMERIC(14, 2) | no |  |
| `selling_price` | NUMERIC(14, 2) | no |  |
| `mrp` | NUMERIC(14, 2) | yes |  |
| `tax_rate_id` | INTEGER | yes | FK → `tax_rates.id` |
| `discount_percent` | NUMERIC(6, 2) | no |  |
| `min_stock` | NUMERIC(14, 3) | no |  |
| `max_stock` | NUMERIC(14, 3) | yes |  |
| `reorder_level` | NUMERIC(14, 3) | no |  |
| `supplier_id` | INTEGER | yes | FK → `suppliers.id` |
| `image_path` | VARCHAR(255) | yes |  |
| `track_expiry` | BOOLEAN | no |  |
| `track_batch` | BOOLEAN | no |  |
| `is_active` | BOOLEAN | no | indexed |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `is_deleted` | BOOLEAN | no | indexed |
| `deleted_at` | DATETIME | yes |  |

Constraints: check `purchase_price >= 0`; check `selling_price >= 0`

## `promotions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `name` | VARCHAR(120) | no |  |
| `promo_type` | VARCHAR(20) | no |  |
| `product_id` | INTEGER | yes | FK → `products.id` |
| `category_id` | INTEGER | yes | FK → `product_categories.id` |
| `buy_quantity` | NUMERIC(14, 3) | no |  |
| `get_quantity` | NUMERIC(14, 3) | no |  |
| `value` | NUMERIC(14, 2) | no |  |
| `start_at` | DATETIME | yes |  |
| `end_at` | DATETIME | yes |  |
| `days_of_week` | VARCHAR(20) | yes |  |
| `start_time` | VARCHAR(5) | yes |  |
| `end_time` | VARCHAR(5) | yes |  |
| `priority` | INTEGER | no |  |
| `is_active` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `purchase_items`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `purchase_id` | INTEGER | no | FK → `purchase_orders.id`, indexed |
| `product_id` | INTEGER | no | FK → `products.id` |
| `quantity` | NUMERIC(14, 3) | no |  |
| `received_quantity` | NUMERIC(14, 3) | no |  |
| `returned_quantity` | NUMERIC(14, 3) | no |  |
| `received_value` | NUMERIC(14, 2) | no |  |
| `unit_cost` | NUMERIC(14, 2) | no |  |
| `discount_amount` | NUMERIC(14, 2) | no |  |
| `tax_rate` | NUMERIC(6, 2) | no |  |
| `tax_amount` | NUMERIC(14, 2) | no |  |
| `line_total` | NUMERIC(14, 2) | no |  |

## `purchase_orders`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `po_number` | VARCHAR(30) | no | unique |
| `supplier_id` | INTEGER | no | FK → `suppliers.id`, indexed |
| `status` | VARCHAR(25) | no | indexed |
| `order_date` | DATE | no |  |
| `expected_date` | DATE | yes |  |
| `subtotal` | NUMERIC(14, 2) | no |  |
| `discount_amount` | NUMERIC(14, 2) | no |  |
| `tax_amount` | NUMERIC(14, 2) | no |  |
| `total_amount` | NUMERIC(14, 2) | no |  |
| `received_value` | NUMERIC(14, 2) | no |  |
| `paid_amount` | NUMERIC(14, 2) | no |  |
| `notes` | TEXT | yes |  |
| `created_by` | INTEGER | yes | FK → `users.id` |
| `approved_by` | INTEGER | yes | FK → `users.id` |
| `approved_at` | DATETIME | yes |  |
| `cancelled_reason` | TEXT | yes |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `purchase_return_items`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `return_id` | INTEGER | no | FK → `purchase_returns.id`, indexed |
| `purchase_item_id` | INTEGER | yes | FK → `purchase_items.id` |
| `product_id` | INTEGER | no | FK → `products.id` |
| `batch_id` | INTEGER | yes | FK → `inventory_batches.id` |
| `quantity` | NUMERIC(14, 3) | no |  |
| `unit_cost` | NUMERIC(14, 2) | no |  |
| `amount` | NUMERIC(14, 2) | no |  |

## `purchase_returns`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `return_number` | VARCHAR(30) | no | unique |
| `supplier_id` | INTEGER | no | FK → `suppliers.id`, indexed |
| `purchase_id` | INTEGER | yes | FK → `purchase_orders.id` |
| `return_date` | DATE | no |  |
| `total_amount` | NUMERIC(14, 2) | no |  |
| `reason` | TEXT | no |  |
| `created_by` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `refresh_tokens`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `user_id` | INTEGER | no | FK → `users.id`, indexed |
| `token_hash` | VARCHAR(64) | no | unique |
| `expires_at` | DATETIME | no |  |
| `revoked_at` | DATETIME | yes |  |
| `ip_address` | VARCHAR(64) | yes |  |
| `user_agent` | VARCHAR(255) | yes |  |
| `created_at` | DATETIME | no |  |
| `last_used_at` | DATETIME | yes |  |

## `role_permissions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `role_id` | INTEGER | no | PK, FK → `roles.id` |
| `permission_id` | INTEGER | no | PK, FK → `permissions.id` |

## `roles`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `name` | VARCHAR(60) | no | unique, indexed |
| `description` | VARCHAR(255) | no |  |
| `is_system` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `sale_item_allocations`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `sale_item_id` | INTEGER | no | FK → `sale_items.id`, indexed |
| `batch_id` | INTEGER | yes | FK → `inventory_batches.id` |
| `quantity` | NUMERIC(14, 3) | no |  |
| `returned_quantity` | NUMERIC(14, 3) | no |  |
| `unit_cost` | NUMERIC(14, 2) | no |  |

## `sale_items`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `sale_id` | INTEGER | no | FK → `sales.id`, indexed |
| `product_id` | INTEGER | no | FK → `products.id`, indexed |
| `product_name` | VARCHAR(200) | no |  |
| `sku` | VARCHAR(60) | no |  |
| `quantity` | NUMERIC(14, 3) | no |  |
| `returned_quantity` | NUMERIC(14, 3) | no |  |
| `unit_price` | NUMERIC(14, 2) | no |  |
| `unit_cost` | NUMERIC(14, 2) | no |  |
| `discount_amount` | NUMERIC(14, 2) | no |  |
| `promotion_id` | INTEGER | yes | FK → `promotions.id` |
| `tax_rate` | NUMERIC(6, 2) | no |  |
| `tax_amount` | NUMERIC(14, 2) | no |  |
| `line_total` | NUMERIC(14, 2) | no |  |
| `cogs_amount` | NUMERIC(14, 2) | no |  |
| `returned_amount` | NUMERIC(14, 2) | no |  |

Constraints: check `quantity > 0`

## `sale_payments`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `sale_id` | INTEGER | no | FK → `sales.id`, indexed |
| `payment_method_id` | INTEGER | no | FK → `payment_methods.id`, indexed |
| `amount` | NUMERIC(14, 2) | no |  |
| `reference_number` | VARCHAR(80) | yes |  |
| `transaction_id` | VARCHAR(80) | yes |  |
| `user_id` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no |  |

## `sale_return_items`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `return_id` | INTEGER | no | FK → `sale_returns.id`, indexed |
| `sale_item_id` | INTEGER | no | FK → `sale_items.id` |
| `product_id` | INTEGER | no | FK → `products.id` |
| `quantity` | NUMERIC(14, 3) | no |  |
| `amount` | NUMERIC(14, 2) | no |  |
| `cogs_amount` | NUMERIC(14, 2) | no |  |
| `tax_amount` | NUMERIC(14, 2) | no |  |

## `sale_returns`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `return_number` | VARCHAR(30) | no | unique |
| `sale_id` | INTEGER | no | FK → `sales.id`, indexed |
| `customer_id` | INTEGER | yes | FK → `customers.id` |
| `session_id` | INTEGER | yes | FK → `cash_register_sessions.id` |
| `total_amount` | NUMERIC(14, 2) | no |  |
| `tax_amount` | NUMERIC(14, 2) | no |  |
| `cogs_amount` | NUMERIC(14, 2) | no |  |
| `due_reduced` | NUMERIC(14, 2) | no |  |
| `refunded_amount` | NUMERIC(14, 2) | no |  |
| `refund_method_id` | INTEGER | yes | FK → `payment_methods.id` |
| `reason` | TEXT | no |  |
| `created_by` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `sales`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `invoice_number` | VARCHAR(30) | no | unique |
| `client_ref` | VARCHAR(64) | yes | unique |
| `sale_date` | DATETIME | no |  |
| `customer_id` | INTEGER | yes | FK → `customers.id`, indexed |
| `cashier_id` | INTEGER | no | FK → `users.id`, indexed |
| `session_id` | INTEGER | yes | FK → `cash_register_sessions.id` |
| `status` | VARCHAR(15) | no | indexed |
| `return_status` | VARCHAR(10) | no |  |
| `subtotal` | NUMERIC(14, 2) | no |  |
| `discount_amount` | NUMERIC(14, 2) | no |  |
| `tax_amount` | NUMERIC(14, 2) | no |  |
| `total_amount` | NUMERIC(14, 2) | no |  |
| `cogs_amount` | NUMERIC(14, 2) | no |  |
| `paid_amount` | NUMERIC(14, 2) | no |  |
| `due_amount` | NUMERIC(14, 2) | no |  |
| `tendered_amount` | NUMERIC(14, 2) | no |  |
| `change_amount` | NUMERIC(14, 2) | no |  |
| `returned_amount` | NUMERIC(14, 2) | no |  |
| `notes` | TEXT | yes |  |
| `void_reason` | TEXT | yes |  |
| `voided_by` | INTEGER | yes | FK → `users.id` |
| `voided_at` | DATETIME | yes |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `settings`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `key` | VARCHAR(100) | no | unique, indexed |
| `value` | JSON | no |  |
| `group` | VARCHAR(50) | no |  |
| `is_public` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `stock_adjustments`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `adjustment_number` | VARCHAR(30) | no | unique |
| `product_id` | INTEGER | no | FK → `products.id`, indexed |
| `batch_id` | INTEGER | yes | FK → `inventory_batches.id` |
| `adjustment_type` | VARCHAR(20) | no |  |
| `quantity` | NUMERIC(14, 3) | no |  |
| `reason` | TEXT | no |  |
| `user_id` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no | indexed |

## `supplier_products`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `supplier_id` | INTEGER | no | FK → `suppliers.id`, indexed |
| `product_id` | INTEGER | no | FK → `products.id`, indexed |
| `supplier_sku` | VARCHAR(60) | yes |  |
| `last_cost` | NUMERIC(14, 2) | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints: unique(supplier_id, product_id)

## `supplier_transactions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `supplier_id` | INTEGER | no | FK → `suppliers.id` |
| `txn_type` | VARCHAR(20) | no |  |
| `amount` | NUMERIC(14, 2) | no |  |
| `balance_after` | NUMERIC(14, 2) | no |  |
| `reference_type` | VARCHAR(30) | yes |  |
| `reference_id` | INTEGER | yes |  |
| `reference_number` | VARCHAR(40) | yes |  |
| `notes` | TEXT | yes |  |
| `user_id` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no | indexed |

## `suppliers`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `code` | VARCHAR(30) | no | unique |
| `name` | VARCHAR(150) | no | indexed |
| `company` | VARCHAR(150) | yes |  |
| `phone` | VARCHAR(30) | yes | indexed |
| `email` | VARCHAR(255) | yes |  |
| `address` | TEXT | yes |  |
| `contact_person` | VARCHAR(150) | yes |  |
| `tax_id` | VARCHAR(50) | yes |  |
| `opening_balance` | NUMERIC(14, 2) | no |  |
| `balance` | NUMERIC(14, 2) | no |  |
| `payment_terms_days` | INTEGER | no |  |
| `notes` | TEXT | yes |  |
| `is_active` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `is_deleted` | BOOLEAN | no | indexed |
| `deleted_at` | DATETIME | yes |  |

## `tax_rates`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `name` | VARCHAR(80) | no |  |
| `rate` | NUMERIC(6, 2) | no |  |
| `effective_from` | DATE | yes |  |
| `effective_to` | DATE | yes |  |
| `is_active` | BOOLEAN | no |  |
| `is_default` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `uploaded_files`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `stored_name` | VARCHAR(120) | no | unique |
| `original_name` | VARCHAR(255) | no |  |
| `content_type` | VARCHAR(80) | no |  |
| `size` | INTEGER | no |  |
| `uploaded_by` | INTEGER | yes | FK → `users.id` |
| `created_at` | DATETIME | no |  |

## `user_roles`

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | INTEGER | no | PK, FK → `users.id` |
| `role_id` | INTEGER | no | PK, FK → `roles.id` |

## `users`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | no | PK |
| `email` | VARCHAR(255) | no | unique, indexed |
| `full_name` | VARCHAR(150) | no |  |
| `phone` | VARCHAR(30) | yes |  |
| `password_hash` | VARCHAR(255) | no |  |
| `is_active` | BOOLEAN | no |  |
| `must_change_password` | BOOLEAN | no |  |
| `failed_login_attempts` | INTEGER | no |  |
| `locked_until` | DATETIME | yes |  |
| `last_login_at` | DATETIME | yes |  |
| `totp_secret` | VARCHAR(64) | yes |  |
| `totp_enabled` | BOOLEAN | no |  |
| `language` | VARCHAR(5) | no |  |
| `max_discount_percent` | NUMERIC(14, 2) | yes |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `is_deleted` | BOOLEAN | no | indexed |
| `deleted_at` | DATETIME | yes |  |

