"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Plus } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { AsyncCombobox, type Option } from "@/components/shared/combobox"
import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { FormDialog, SubmitRow } from "@/components/shared/dialogs"
import { DateRangeFilter, type DateRange } from "@/components/shared/filters"
import { Can, Field, Money, NativeSelect, PageHeader, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDate, formatDateTime, formatNumber } from "@/lib/format"
import { useT } from "@/lib/i18n"
import { optionalNumber, searchProducts, useCategories } from "@/services/lookups"
import type { Adjustment, Batch, Movement, Product, StockRow } from "@/types/api"

const TYPE_TONE: Record<string, "success" | "danger" | "warning" | "info" | "neutral"> = {
  PURCHASE: "success", SALE_RETURN: "success", ADJUSTMENT_IN: "success", SALE: "info", SALE_VOID: "warning", PURCHASE_RETURN: "warning",
  ADJUSTMENT_OUT: "neutral", DAMAGE: "danger", EXPIRED: "danger",
}

/* -------------------------------- stock -------------------------------- */

export function StockPage() {
  const t = useT()
  const { can } = useAuth()
  const [status, setStatus] = useState("")
  const [category, setCategory] = useState("")
  const cats = useCategories()
  const { query, data, setPage, search, setSearch } = useTableQuery<StockRow>("stock", "/inventory/stock", { filters: { status: status || undefined, category_id: category || undefined } })
  const cost = can("product.cost")
  return (
    <>
      <PageHeader title={t("nav.inventory.stock")} description="Current stock by product, including damaged and expired quantities."
        actions={<Can perm="inventory.adjust"><Button render={<Link href="/inventory/adjustments" />}><Plus className="size-4" /> Adjust stock</Button></Can>} />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search product, SKU or barcode…" />
        <NativeSelect aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} className="w-44"><option value="">All categories</option>{cats.data?.filter((c) => c.parent_id === null).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect>
        <NativeSelect aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-40"><option value="">All statuses</option><option value="ok">Healthy</option><option value="low">Low stock</option><option value="out">Out of stock</option></NativeSelect>
      </Toolbar>
      <StockTable query={query} data={data} setPage={setPage} cost={cost} />
    </>
  )
}

function StockTable({ query, data, setPage, cost }: { query: ReturnType<typeof useTableQuery<StockRow>>["query"]; data: ReturnType<typeof useTableQuery<StockRow>>["data"]; setPage: (n: number) => void; cost: boolean }) {
  return (
    <DataTable<StockRow>
      page={data} isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(r) => r.product_id}
      empty={{ title: "No products match.", description: "Try a different filter or search." }}
      columns={[
        { id: "name", header: "Product", cell: (r) => <Link href={`/products/${r.product_id}`} className="block min-w-0 hover:underline"><span className="block truncate font-medium">{r.name}</span><span className="block font-mono text-xs text-muted-foreground">{r.sku}</span></Link> },
        { id: "cat", header: "Category", cell: (r) => r.category ?? "—", hideOnMobile: true },
        { id: "stock", header: "In stock", align: "right", cell: (r) => <span className="font-medium tabular">{formatNumber(r.current_stock)} <span className="text-xs font-normal text-muted-foreground">{r.unit}</span></span> },
        { id: "reorder", header: "Reorder at", align: "right", cell: (r) => <span className="tabular text-muted-foreground">{formatNumber(r.reorder_level)}</span>, hideOnMobile: true },
        { id: "damaged", header: "Damaged", align: "right", cell: (r) => (r.damaged_stock ? formatNumber(r.damaged_stock) : "—"), hideOnMobile: true },
        { id: "expired", header: "Expired", align: "right", cell: (r) => (r.expired_stock ? formatNumber(r.expired_stock) : "—"), hideOnMobile: true },
        ...(cost ? [{ id: "value", header: "Value", align: "right" as const, cell: (r: StockRow) => <Money value={r.stock_value} />, hideOnMobile: true }] : []),
        { id: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
      ]}
    />
  )
}

export function LowStockPage() {
  const { can } = useAuth()
  const { query, data, setPage, search, setSearch } = useTableQuery<StockRow>("low-stock", "/inventory/low-stock")
  return (
    <>
      <PageHeader title="Low stock" description="Products at or below their reorder level. Restock them before they run out." actions={<Can perm="purchase.create"><Button render={<Link href="/purchases/new" />}><Plus className="size-4" /> New purchase order</Button></Can>} />
      <Toolbar><SearchInput value={search} onChange={setSearch} /></Toolbar>
      <StockTable query={query} data={data} setPage={setPage} cost={can("product.cost")} />
    </>
  )
}

/* ------------------------------ expiry pages ------------------------------ */

function ExpiryTable({ path, title, description, emptyTitle, showDays }: { path: string; title: string; description: string; emptyTitle: string; showDays?: boolean }) {
  const { can } = useAuth()
  const [days, setDays] = useState("")
  const { query, data, setPage, search, setSearch } = useTableQuery<Batch>(path.replace(/\//g, "-"), path, { filters: { days: days || undefined } })
  return (
    <>
      <PageHeader title={title} description={description} />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} />
        {showDays && (
          <NativeSelect aria-label="Window" value={days} onChange={(e) => setDays(e.target.value)} className="w-44">
            <option value="">Default window</option>{[7, 15, 30, 60, 90].map((d) => <option key={d} value={d}>Next {d} days</option>)}
          </NativeSelect>
        )}
      </Toolbar>
      <DataTable<Batch>
        page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(b) => b.id}
        empty={{ title: emptyTitle, description: "Nothing needs attention right now." }}
        columns={[
          { id: "p", header: "Product", cell: (b) => <Link href={`/products/${b.product_id}`} className="block hover:underline"><span className="font-medium">{b.product_name}</span><span className="block font-mono text-xs text-muted-foreground">{b.sku}</span></Link> },
          { id: "batch", header: "Batch", cell: (b) => <span className="font-mono text-xs">{b.batch_number}</span> },
          { id: "expiry", header: "Expiry", cell: (b) => formatDate(b.expiry_date) },
          { id: "days", header: "Days left", align: "right", cell: (b) => <span className={(b.days_to_expiry ?? 0) < 0 ? "font-medium text-destructive" : (b.days_to_expiry ?? 99) <= 7 ? "font-medium text-warning" : ""}>{b.days_to_expiry}</span> },
          { id: "qty", header: "Qty", align: "right", cell: (b) => formatNumber(b.quantity_remaining) },
          ...(can("product.cost") ? [{ id: "value", header: "Value at cost", align: "right" as const, cell: (b: Batch) => <Money value={b.stock_value} />, hideOnMobile: true }] : []),
        ]}
      />
    </>
  )
}

export const ExpiringPage = () => <ExpiryTable path="/inventory/expiring" title="Expiring soon" description="Batches close to their expiry date — sell them first or mark them down." emptyTitle="No batches are expiring soon." showDays />
export const ExpiredPage = () => <ExpiryTable path="/inventory/expired" title="Expired stock" description="Expired batches are blocked from sale. Write them off with an ‘Expired’ stock adjustment." emptyTitle="No expired stock." />

/* -------------------------------- movements -------------------------------- */

export function MovementsPage() {
  const { can } = useAuth()
  const [type, setType] = useState("")
  const [range, setRange] = useState<DateRange>({ start: "", end: "" })
  const rangeOk = !!range.start && !!range.end
  const { query, data, setPage, search, setSearch } = useTableQuery<Movement>("movements", "/inventory/movements", {
    filters: { txn_type: type || undefined, start: rangeOk ? range.start : undefined, end: rangeOk ? range.end : undefined }, pageSize: 30,
  })
  return (
    <>
      <PageHeader title="Stock movements" description="The immutable stock ledger: every receipt, sale, return and adjustment." />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search product or SKU…" />
        <NativeSelect aria-label="Movement type" value={type} onChange={(e) => setType(e.target.value)} className="w-48">
          <option value="">All types</option>{Object.keys(TYPE_TONE).map((tp) => <option key={tp} value={tp}>{tp.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}</option>)}
        </NativeSelect>
        <DateRangeFilter value={range} onChange={setRange} />
      </Toolbar>
      <DataTable<Movement>
        page={data} isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(m) => m.id}
        empty={{ title: "No stock movements found." }}
        columns={[
          { id: "date", header: "Date", cell: (m) => <span className="whitespace-nowrap">{formatDateTime(m.created_at)}</span> },
          { id: "p", header: "Product", cell: (m) => <Link href={`/products/${m.product_id}`} className="block hover:underline"><span className="font-medium">{m.product_name}</span><span className="block font-mono text-xs text-muted-foreground">{m.sku}{m.batch_number ? ` · ${m.batch_number}` : ""}</span></Link> },
          { id: "type", header: "Type", cell: (m) => <StatusBadge status={m.txn_type} tone={TYPE_TONE[m.txn_type] ?? "neutral"} /> },
          { id: "qty", header: "Qty", align: "right", cell: (m) => <span className={`tabular font-medium ${m.quantity > 0 ? "text-success" : ""}`}>{m.quantity > 0 ? "+" : ""}{formatNumber(m.quantity)}</span> },
          { id: "bal", header: "Balance", align: "right", cell: (m) => <span className="tabular">{formatNumber(m.balance_after)}</span> },
          ...(can("product.cost") ? [{ id: "cost", header: "Unit cost", align: "right" as const, cell: (m: Movement) => <Money value={m.unit_cost} className="text-muted-foreground" />, hideOnMobile: true }] : []),
          { id: "reason", header: "Reason / reference", cell: (m) => <span className="text-muted-foreground">{m.reason ?? (m.reference_type ? `${m.reference_type} #${m.reference_id}` : "—")}</span>, hideOnMobile: true },
          { id: "user", header: "By", cell: (m) => m.user_name ?? "—", hideOnMobile: true },
        ]}
      />
    </>
  )
}

/* ------------------------------- adjustments ------------------------------- */

const adjSchema = z.object({
  adjustment_type: z.enum(["IN", "OUT", "DAMAGE", "EXPIRED"]),
  quantity: z.number({ error: "Enter a quantity" }).positive("Must be greater than zero"),
  reason: z.string().trim().min(3, "A reason is required (at least 3 characters)").max(500),
  batch_id: z.number().optional(),
  unit_cost: z.number().min(0).optional(),
  expiry_date: z.string().optional(),
  batch_number: z.string().max(60).optional(),
})
type AdjValues = z.infer<typeof adjSchema>

const ADJ_LABEL: Record<AdjValues["adjustment_type"], string> = {
  IN: "Stock in (found / correction up)", OUT: "Stock out (correction down)", DAMAGE: "Damaged", EXPIRED: "Expired write-off",
}

function AdjustmentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { can } = useAuth()
  const [product, setProduct] = useState<Option | null>(null)
  const [detail, setDetail] = useState<Product | null>(null)
  const [productError, setProductError] = useState<string>()
  const { register, handleSubmit, watch, reset, formState: { errors } } = useForm<AdjValues>({ resolver: zodResolver(adjSchema), defaultValues: { adjustment_type: "OUT", reason: "" } })
  const type = watch("adjustment_type")
  const save = useApiMutation(
    (v: AdjValues) => api.post("/inventory/adjustments", { ...v, product_id: product!.id, expiry_date: v.expiry_date || undefined, batch_number: v.batch_number || undefined }),
    { success: "Stock adjusted", invalidate: [["stock"], ["adjustments"], ["products"], ["movements"], ["dashboard"], ["low-stock"]], onSuccess: () => { reset(); setProduct(null); setDetail(null); onClose() } },
  )
  async function pick(o: Option | null) {
    setProduct(o)
    setProductError(undefined)
    setDetail(o ? await api.get<Product>(`/products/${o.id}`) : null)
  }
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title="Adjust stock" description="Every adjustment needs a reason and is written to the stock ledger and audit log.">
      <form onSubmit={handleSubmit((v) => { if (!product) { setProductError("Choose a product"); return } save.mutate(v) })} className="space-y-4" noValidate>
        <Field label="Product" required error={productError}>{(p) => <AsyncCombobox id={p.id} invalid={p["aria-invalid"]} value={product} onChange={pick} fetcher={searchProducts} queryKey="products" placeholder="Search product…" />}</Field>
        {detail && <p className="-mt-2 text-xs text-muted-foreground">Currently {formatNumber(detail.current_stock)} {detail.unit.short_name} in stock.</p>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Adjustment type" required>{(p) => <NativeSelect {...p} {...register("adjustment_type")}>{Object.entries(ADJ_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect>}</Field>
          <Field label="Quantity" required error={errors.quantity?.message}>{(p) => <Input {...p} type="number" step="any" min="0" inputMode="decimal" {...register("quantity", { setValueAs: optionalNumber })} />}</Field>
        </div>
        {type === "IN" && (
          <div className="grid gap-4 sm:grid-cols-3">
            {can("product.cost") && <Field label="Unit cost" error={errors.unit_cost?.message} hint="Defaults to current cost">{(p) => <Input {...p} type="number" step="0.01" min="0" {...register("unit_cost", { setValueAs: optionalNumber })} />}</Field>}
            <Field label="Batch no.">{(p) => <Input {...p} {...register("batch_number")} />}</Field>
            {detail?.track_expiry && <Field label="Expiry date" required>{(p) => <Input {...p} type="date" {...register("expiry_date")} />}</Field>}
          </div>
        )}
        <Field label="Reason" required error={errors.reason?.message}>{(p) => <Textarea {...p} rows={2} placeholder="e.g. Stock count correction, dropped in storeroom…" {...register("reason")} />}</Field>
        <SubmitRow onCancel={onClose} submitting={save.isPending} submitLabel="Apply adjustment" />
      </form>
    </FormDialog>
  )
}

export function AdjustmentsPage() {
  const [open, setOpen] = useState(false)
  const { query, data, setPage, search, setSearch } = useTableQuery<Adjustment>("adjustments", "/inventory/adjustments")
  return (
    <>
      <PageHeader title="Stock adjustments" description="Manual corrections, damage and expiry write-offs."
        actions={<Can perm="inventory.adjust"><Button onClick={() => setOpen(true)}><Plus className="size-4" /> New adjustment</Button></Can>} />
      <Toolbar><SearchInput value={search} onChange={setSearch} placeholder="Search product or adjustment no…" /></Toolbar>
      <DataTable<Adjustment>
        page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(a) => a.id}
        empty={{ title: "No adjustments yet.", description: "Adjustments appear here whenever stock is corrected, damaged or written off." }}
        columns={[
          { id: "no", header: "No.", cell: (a) => <span className="font-mono text-xs">{a.adjustment_number}</span> },
          { id: "date", header: "Date", cell: (a) => formatDateTime(a.created_at) },
          { id: "p", header: "Product", cell: (a) => <span className="font-medium">{a.product_name}</span> },
          { id: "type", header: "Type", cell: (a) => <StatusBadge status={a.adjustment_type} tone={a.adjustment_type === "IN" ? "success" : a.adjustment_type === "OUT" ? "neutral" : "danger"} /> },
          { id: "qty", header: "Qty", align: "right", cell: (a) => formatNumber(a.quantity) },
          { id: "reason", header: "Reason", cell: (a) => <span className="text-muted-foreground">{a.reason}</span>, hideOnMobile: true },
          { id: "by", header: "By", cell: (a) => a.user_name ?? "—", hideOnMobile: true },
        ]}
      />
      <AdjustmentDialog open={open} onClose={() => setOpen(false)} />
    </>
  )
}
