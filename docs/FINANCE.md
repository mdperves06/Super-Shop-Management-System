# How the numbers are calculated

All figures below are computed on the backend (`app/services/pricing.py`, `financials.py`, `report_service.py`); the UI never does its own arithmetic. Tests reproduce the examples.

## A sale line

```
gross            = unit price × quantity
automatic disc.  = max(product standing %, customer standing %, best live promotion)   # they don't stack
manual disc.     = cashier's line discount                                              # counts toward the cashier limit
invoice disc.    = share of the invoice-level discount, pro-rata (last line takes the rounding remainder)
net              = gross − automatic − manual − invoice discount

VAT included in price (default):   VAT = net × r / (100 + r) ,  line total = net
VAT added on top:                  VAT = net × r / 100       ,  line total = net + VAT
```
Everything is rounded half-up to 0.01 per line, and invoice totals are the sum of lines.

## Profit — one formula

```
revenue       = Σ (line total − VAT)                      of completed sales in the period
net revenue   = revenue − Σ (returned value − returned VAT)   (returns count on the day they happen)
COGS          = Σ cost of the batches actually sold − cost of goods returned
gross profit  = net revenue − COGS                          ← pricing.gross_profit()
net profit    = gross profit − active expenses
```
Worked example (tests `test_spec_profit_example_with_discount`): price 150, cost 100, qty 10 → revenue 1 500, COGS 1 000, profit 500. With a ৳100 discount → revenue 1 400, profit 400.

Voided sales disappear from all figures. The dashboard, profit report and sales summary use the same functions and are asserted equal in tests.

## Inventory valuation

`Σ quantity_remaining × batch cost` over batches (FIFO; FEFO order for expiry-tracked products). Batch cost for a received purchase line = `(unit cost × qty − line discount) / qty` — purchase VAT is excluded from stock cost and included in the supplier payable.

## Ledgers

* **Supplier** (we owe): purchase receipt `+value`, payment `−amount`, purchase return `−credit`, adjustment `±`. Opening balance seeds the ledger.
* **Customer** (they owe): sale `+total`, checkout payment `−paid`, later payment `−amount`, return `−value`, cash refund `+amount` (money leaves the shop), void reverses both sale legs.
* Each row stores `balance_after`; `balance = Σ amount` always.

Return arithmetic: refund value of the last unit of a line is `line total − already returned`, so partial returns never drift by a paisa. A return first reduces the invoice's unpaid balance (`due_reduced`) and refunds only the rest.

## Cash register

`expected cash = opening cash + cash sales − cash refunds − cash expenses ± cash in/out ± cash collected from customers − cash paid to suppliers − cash voids`. Only *cash*-type payment methods touch the drawer (card/bKash sales do not). Closing stores expected, counted and the signed difference; a non-zero difference requires a reason and creates a notification and audit entry.

## Numbering

`PREFIX-YYYY-000001` from an atomic counter per prefix and year: invoices `INV`, purchases `PUR`, sale returns `RET`, purchase returns `PRET`, goods receipts `GRN`, expenses `EXP`, payments `PAY`/`RCV`, adjustments `ADJ`, suppliers `SUP`, customers `CUS`, employees `EMP`. Prefixes for invoice/purchase/return are configurable.
