# REST API

_Generated from the FastAPI OpenAPI schema by `backend/scripts/gen_docs.py`._

Interactive docs (Swagger UI) are served at `/docs` and `/redoc` whenever `ENVIRONMENT` is not `production`; the raw schema is `/openapi.json`.

## Conventions

- Base path `/api/v1`. JSON in, JSON out. Authenticate with `Authorization: Bearer <access token>` (get one from `POST /auth/login`).
- **Lists** return `{items, total, page, page_size, pages}` and accept `page`, `page_size` (max 200), `search`, `sort` (`name` / `-name`) plus route-specific filters.
- **Errors** always look like `{"error": {"code": "insufficient_stock", "message": "...", "details": {...}, "request_id": "..."}}`. Common codes: `validation_error` (422), `unauthorized` (401), `forbidden` (403), `not_found` (404), `conflict` / `duplicate_sku` / `duplicate_barcode` / `insufficient_stock` (409), `rate_limited` (429).
- **Money and quantities** are JSON numbers. The server computes every total, discount, tax, profit and balance — never trust or send client-side totals.
- Timestamps are ISO-8601 UTC (`...Z`); date-only fields are `YYYY-MM-DD`.
- `POST /sales` accepts an optional `client_ref` (idempotency key) so a retried request cannot create two invoices.

## admin

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/admin/backups` | Create backup |
| `GET` | `/api/v1/admin/backups` | List backups |
| `GET` | `/api/v1/admin/backups/{name}/download` | Download backup |
| `POST` | `/api/v1/admin/backups/{name}/restore` | Restore backup |
| `POST` | `/api/v1/admin/import/{kind}` | Import csv |
| `GET` | `/api/v1/admin/import/{kind}/template` | Import template |

## analytics

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/dashboard` | Dashboard |
| `GET` | `/api/v1/exports/{dataset}` | Export dataset |
| `GET` | `/api/v1/notifications` | List notifications |
| `POST` | `/api/v1/notifications/read-all` | Mark all read |
| `GET` | `/api/v1/notifications/unread-count` | Unread count |
| `POST` | `/api/v1/notifications/{notification_id}/read` | Mark read |
| `GET` | `/api/v1/reports` | Report catalog |
| `GET` | `/api/v1/reports/{name}` | Run report |
| `GET` | `/api/v1/search` | Global search |

## auth

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/auth/2fa/disable` | Totp disable |
| `POST` | `/api/v1/auth/2fa/enable` | Totp enable |
| `POST` | `/api/v1/auth/2fa/setup` | Totp setup |
| `POST` | `/api/v1/auth/change-password` | Change password |
| `POST` | `/api/v1/auth/forgot-password` | Forgot password |
| `POST` | `/api/v1/auth/login` | Login |
| `POST` | `/api/v1/auth/logout` | Logout |
| `GET` | `/api/v1/auth/me` | Me |
| `PATCH` | `/api/v1/auth/me` | Update me |
| `POST` | `/api/v1/auth/refresh` | Refresh |
| `POST` | `/api/v1/auth/reset-password` | Reset password |
| `GET` | `/api/v1/auth/sessions` | My sessions |
| `DELETE` | `/api/v1/auth/sessions/{session_id}` | Revoke session |

## catalog

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/brands` | Create brand |
| `GET` | `/api/v1/brands` | List brands |
| `PUT` | `/api/v1/brands/{brand_id}` | Update brand |
| `DELETE` | `/api/v1/brands/{brand_id}` | Delete brand |
| `POST` | `/api/v1/categories` | Create category |
| `GET` | `/api/v1/categories` | List categories |
| `PUT` | `/api/v1/categories/{category_id}` | Update category |
| `DELETE` | `/api/v1/categories/{category_id}` | Delete category |
| `POST` | `/api/v1/products` | Create product |
| `GET` | `/api/v1/products` | List products |
| `GET` | `/api/v1/products/generate-barcode` | Generate barcode |
| `GET` | `/api/v1/products/lookup` | Lookup products |
| `GET` | `/api/v1/products/{product_id}` | Get product |
| `PATCH` | `/api/v1/products/{product_id}` | Update product |
| `DELETE` | `/api/v1/products/{product_id}` | Delete product |
| `POST` | `/api/v1/products/{product_id}/barcodes` | Add barcode |
| `DELETE` | `/api/v1/products/{product_id}/barcodes/{barcode_id}` | Remove barcode |
| `POST` | `/api/v1/products/{product_id}/image` | Upload image |
| `POST` | `/api/v1/tax-rates` | Create tax rate |
| `GET` | `/api/v1/tax-rates` | List tax rates |
| `PUT` | `/api/v1/tax-rates/{tax_id}` | Update tax rate |
| `POST` | `/api/v1/units` | Create unit |
| `GET` | `/api/v1/units` | List units |
| `PUT` | `/api/v1/units/{unit_id}` | Update unit |

## customers

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/customers` | Create customer |
| `GET` | `/api/v1/customers` | List customers |
| `GET` | `/api/v1/customers/{customer_id}` | Customer profile |
| `PATCH` | `/api/v1/customers/{customer_id}` | Update customer |
| `DELETE` | `/api/v1/customers/{customer_id}` | Delete customer |
| `POST` | `/api/v1/customers/{customer_id}/addresses` | Add address |
| `DELETE` | `/api/v1/customers/{customer_id}/addresses/{address_id}` | Delete address |
| `POST` | `/api/v1/customers/{customer_id}/adjustments` | Adjust customer balance |
| `GET` | `/api/v1/customers/{customer_id}/ledger` | Customer ledger |
| `POST` | `/api/v1/customers/{customer_id}/payments` | Receive payment |
| `GET` | `/api/v1/customers/{customer_id}/payments` | Customer payments |

## documents

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/documents/customers/{customer_id}/statement.pdf` | Customer statement |
| `GET` | `/api/v1/documents/purchases/{purchase_id}/invoice.pdf` | Purchase invoice |
| `GET` | `/api/v1/documents/sales/{sale_id}/invoice.pdf` | Invoice |
| `GET` | `/api/v1/documents/sales/{sale_id}/receipt.pdf` | Receipt |
| `GET` | `/api/v1/documents/suppliers/{supplier_id}/statement.pdf` | Supplier statement |

## expenses-employees

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/employees` | Create employee |
| `GET` | `/api/v1/employees` | List employees |
| `GET` | `/api/v1/employees/{employee_id}` | Get employee |
| `PATCH` | `/api/v1/employees/{employee_id}` | Update employee |
| `DELETE` | `/api/v1/employees/{employee_id}` | Delete employee |
| `GET` | `/api/v1/employees/{employee_id}/activity` | Employee activity |
| `GET` | `/api/v1/employees/{employee_id}/attendance` | Attendance |
| `POST` | `/api/v1/employees/{employee_id}/attendance/check-in` | Check in |
| `POST` | `/api/v1/employees/{employee_id}/attendance/check-out` | Check out |
| `POST` | `/api/v1/expense-categories` | Create expense category |
| `GET` | `/api/v1/expense-categories` | Expense categories |
| `POST` | `/api/v1/expenses` | Create expense |
| `GET` | `/api/v1/expenses` | List expenses |
| `PATCH` | `/api/v1/expenses/{expense_id}` | Update expense |
| `POST` | `/api/v1/expenses/{expense_id}/attachment` | Upload attachment |
| `GET` | `/api/v1/expenses/{expense_id}/attachment` | Get attachment |
| `POST` | `/api/v1/expenses/{expense_id}/void` | Void expense |

## health

| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Health |

## inventory

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/inventory/adjustments` | Create adjustment |
| `GET` | `/api/v1/inventory/adjustments` | List adjustments |
| `GET` | `/api/v1/inventory/batches` | Batches |
| `GET` | `/api/v1/inventory/expired` | Expired |
| `GET` | `/api/v1/inventory/expiring` | Expiring |
| `GET` | `/api/v1/inventory/low-stock` | Low stock |
| `GET` | `/api/v1/inventory/movements` | Movements |
| `GET` | `/api/v1/inventory/stock` | Stock |
| `GET` | `/api/v1/inventory/summary` | Summary |

## purchasing

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/goods-receipts` | Goods receipts |
| `POST` | `/api/v1/purchase-returns` | Create purchase return |
| `GET` | `/api/v1/purchase-returns` | List purchase returns |
| `POST` | `/api/v1/purchases` | Create purchase |
| `GET` | `/api/v1/purchases` | List purchases |
| `GET` | `/api/v1/purchases/{purchase_id}` | Get purchase |
| `PUT` | `/api/v1/purchases/{purchase_id}` | Update purchase |
| `POST` | `/api/v1/purchases/{purchase_id}/approve` | Approve purchase |
| `POST` | `/api/v1/purchases/{purchase_id}/cancel` | Cancel purchase |
| `POST` | `/api/v1/purchases/{purchase_id}/receive` | Receive purchase |
| `POST` | `/api/v1/purchases/{purchase_id}/submit` | Submit purchase |
| `POST` | `/api/v1/suppliers` | Create supplier |
| `GET` | `/api/v1/suppliers` | List suppliers |
| `GET` | `/api/v1/suppliers/{supplier_id}` | Supplier profile |
| `PATCH` | `/api/v1/suppliers/{supplier_id}` | Update supplier |
| `DELETE` | `/api/v1/suppliers/{supplier_id}` | Delete supplier |
| `POST` | `/api/v1/suppliers/{supplier_id}/adjustments` | Adjust supplier |
| `GET` | `/api/v1/suppliers/{supplier_id}/ledger` | Supplier ledger |
| `POST` | `/api/v1/suppliers/{supplier_id}/payments` | Pay supplier |
| `GET` | `/api/v1/suppliers/{supplier_id}/payments` | Supplier payments |

## sales

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/cash-sessions` | List sessions |
| `GET` | `/api/v1/cash-sessions/current` | Current session |
| `POST` | `/api/v1/cash-sessions/open` | Open session |
| `POST` | `/api/v1/cash-sessions/{session_id}/close` | Close session |
| `POST` | `/api/v1/cash-sessions/{session_id}/movements` | Cash movement |
| `POST` | `/api/v1/discounts` | Create discount |
| `GET` | `/api/v1/discounts` | List discounts |
| `DELETE` | `/api/v1/discounts/{discount_id}` | Delete discount |
| `POST` | `/api/v1/promotions` | Create promotion |
| `GET` | `/api/v1/promotions` | List promotions |
| `PUT` | `/api/v1/promotions/{promo_id}` | Update promotion |
| `DELETE` | `/api/v1/promotions/{promo_id}` | Delete promotion |
| `POST` | `/api/v1/registers` | Create register |
| `GET` | `/api/v1/registers` | Registers |
| `POST` | `/api/v1/sale-returns` | Create return |
| `GET` | `/api/v1/sale-returns` | List returns |
| `POST` | `/api/v1/sales` | Create sale |
| `GET` | `/api/v1/sales` | List sales |
| `POST` | `/api/v1/sales/preview` | Preview |
| `GET` | `/api/v1/sales/{sale_id}` | Get sale |
| `POST` | `/api/v1/sales/{sale_id}/void` | Void sale |

## system

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/audit-logs` | Audit logs |
| `POST` | `/api/v1/payment-methods` | Create payment method |
| `GET` | `/api/v1/payment-methods` | Payment methods |
| `PUT` | `/api/v1/payment-methods/{method_id}` | Update payment method |
| `GET` | `/api/v1/settings` | All settings |
| `PUT` | `/api/v1/settings` | Update settings |
| `POST` | `/api/v1/settings/logo` | Upload logo |
| `GET` | `/api/v1/settings/public` | Public settings |

## users

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/permissions` | List permissions |
| `POST` | `/api/v1/roles` | Create role |
| `GET` | `/api/v1/roles` | List roles |
| `PATCH` | `/api/v1/roles/{role_id}` | Update role |
| `DELETE` | `/api/v1/roles/{role_id}` | Delete role |
| `POST` | `/api/v1/users` | Create user |
| `GET` | `/api/v1/users` | List users |
| `GET` | `/api/v1/users/{user_id}` | Get user |
| `PATCH` | `/api/v1/users/{user_id}` | Update user |
| `DELETE` | `/api/v1/users/{user_id}` | Delete user |

