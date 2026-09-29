"use client"

import { useQuery } from "@tanstack/react-query"
import { Ban, FileText, Plus, Printer, Receipt as ReceiptIcon, Undo2 } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { AsyncCombobox, type Option } from "@/components/shared/combobox"
import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { ConfirmDialog, FormDialog } from "@/components/shared/dialogs"
import { DateRangeFilter, type DateRange } from "@/components/shared/filters"
import { PrintPortal, printPage } from "@/components/shared/print"
import { Field, KeyValue, Money, NativeSelect, PageHeader, PageLoading, SectionCard, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { A4Invoice, Receipt } from "@/features/sales/receipt"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api, errorMessage, openFile } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format"
import { useT } from "@/lib/i18n"
import { usePaymentMethods } from "@/services/lookups"
import type { Page, Sale, SaleReturn } from "@/types/api"

const RETURN_TONE: Record<string, "neutral" | "warning" | "danger"> = { NONE: "neutral", PARTIAL: "warning", FULL: "danger" }

export function SalesList() {
  const t = useT()
  const router = useRouter()
  const { can } = useAuth()
  const [status, setStatus] = useState("")
  const [due, setDue] = useState("")
  const [range, setRange] = useState<DateRange>({ start: "", end: "" })
  const ok = !!range.start && !!range.end
  const { query, data, setPage, search, setSearch, sort, toggleSort } = useTableQuery<Sale>("sales", "/sales", {
    filters: { status: status || undefined, has_due: due || undefined, start: ok ? range.start : undefined, end: ok ? range.end : undefined }, defaultSort: "-sale_date",
  })
  return (
    <>
      <PageHeader title={t("nav.sales.all")} description={can("sale.read_all") ? "Every invoice across all cashiers." : "Your invoices."}
        actions={can("sale.create") ? <Button render={<Link href="/pos" />}><Plus className="size-4" /> Open POS</Button> : undefined} />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search invoice, customer or phone…" />
        <NativeSelect aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-36"><option value="">All statuses</option><option value="COMPLETED">Completed</option><option value="VOIDED">Voided</option></NativeSelect>
        <NativeSelect aria-label="Payment" value={due} onChange={(e) => setDue(e.target.value)} className="w-40"><option value="">All payments</option><option value="true">Unpaid balance</option></NativeSelect>
        <DateRangeFilter value={range} onChange={setRange} />
      </Toolbar>
      <DataTable<Sale>
        caption="Sales" page={data} isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} sort={sort} onSort={toggleSort}
        rowKey={(s) => s.id} onRowClick={(s) => router.push(`/sales/${s.id}`)}
        empty={{ title: "No sales found.", description: "Completed sales from the POS appear here.", action: can("sale.create") ? <Button render={<Link href="/pos" />}>Open POS</Button> : undefined }}
        columns={[
          { id: "inv", header: "Invoice", sortKey: "invoice_number", cell: (s) => <span className="font-mono text-xs font-medium">{s.invoice_number}</span> },
          { id: "date", header: "Date", sortKey: "sale_date", cell: (s) => <span className="whitespace-nowrap">{formatDateTime(s.sale_date)}</span> },
          { id: "cust", header: "Customer", cell: (s) => s.customer_name ?? <span className="text-muted-foreground">Walk-in</span>, hideOnMobile: true },
          { id: "cashier", header: "Cashier", cell: (s) => s.cashier_name, hideOnMobile: true },
          { id: "pay", header: "Payment", cell: (s) => [...new Set(s.payments.map((p) => p.method_name))].join(" + ") || "Credit", hideOnMobile: true },
          { id: "total", header: "Total", sortKey: "total_amount", align: "right", cell: (s) => <Money value={s.total_amount} className="font-semibold" /> },
          { id: "due", header: "Due", align: "right", cell: (s) => (s.due_amount > 0 ? <Money value={s.due_amount} className="text-destructive" /> : <span className="text-muted-foreground">—</span>), hideOnMobile: true },
          { id: "status", header: "Status", cell: (s) => <span className="flex flex-wrap gap-1"><StatusBadge status={s.status} />{s.return_status !== "NONE" && <StatusBadge status={s.return_status} tone={RETURN_TONE[s.return_status]} label={s.return_status === "FULL" ? "Returned" : "Part-returned"} />}</span> },
        ]}
      />
    </>
  )
}

export function SaleDetail({ id }: { id: number }) {
  const { can } = useAuth()
  const { data: sale, isLoading, error } = useQuery({ queryKey: ["sales", "detail", id], queryFn: () => api.get<Sale>(`/sales/${id}`) })
  const [returning, setReturning] = useState(false)
  const [voiding, setVoiding] = useState(false)
  const [print, setPrint] = useState<"receipt" | "a4" | null>(null)
  const voidSale = useApiMutation((reason: string) => api.post(`/sales/${id}/void`, { reason }), { success: "Sale voided", invalidate: [["sales"], ["stock"], ["products"], ["dashboard"], ["cash-session"], ["customers"]] })
  if (isLoading) return <PageLoading />
  if (error || !sale) return <p className="mt-10 text-center text-sm text-muted-foreground" role="alert">{errorMessage(error ?? new Error("Sale not found"))}</p>
  const canReturn = sale.status === "COMPLETED" && can("sale.return") && sale.items.some((i) => i.quantity > i.returned_quantity)
  const canVoid = sale.status === "COMPLETED" && sale.return_status === "NONE" && can("sale.cancel")
  const profit = sale.cogs_amount !== null ? sale.total_amount - sale.tax_amount - sale.cogs_amount - 0 : null

  const doPrint = (kind: "receipt" | "a4") => { setPrint(kind); printPage(kind === "receipt" ? "size: 80mm auto; margin: 2mm" : "size: A4; margin: 10mm") }
  return (
    <>
      <PageHeader back={{ href: "/sales", label: "Sales" }}
        title={<span className="flex flex-wrap items-center gap-3">{sale.invoice_number} <StatusBadge status={sale.status} />{sale.return_status !== "NONE" && <StatusBadge status={sale.return_status} tone={RETURN_TONE[sale.return_status]} label={sale.return_status === "FULL" ? "Returned" : "Part-returned"} />}</span>}
        description={`${formatDateTime(sale.sale_date)} · ${sale.cashier_name}${sale.customer_name ? ` · ${sale.customer_name}` : ""}`}
        actions={<>
          <Button variant="outline" onClick={() => doPrint("receipt")}><Printer className="size-4" /> Receipt</Button>
          <Button variant="outline" onClick={() => doPrint("a4")}><ReceiptIcon className="size-4" /> A4 invoice</Button>
          <Button variant="outline" onClick={() => void openFile(`/documents/sales/${id}/invoice.pdf`)}><FileText className="size-4" /> PDF</Button>
          {canReturn && <Button variant="outline" onClick={() => setReturning(true)}><Undo2 className="size-4" /> Return items</Button>}
          {canVoid && <Button variant="destructive" onClick={() => setVoiding(true)}><Ban className="size-4" /> Void sale</Button>}
        </>} />
      {sale.status === "VOIDED" && <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">This sale was voided{sale.void_reason ? `: ${sale.void_reason}` : "."} Stock and payments were reversed; the record is kept for audit.</div>}
      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <SectionCard title="Items">
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="text-xs text-muted-foreground uppercase"><tr className="text-left"><th className="pb-2 font-semibold">Product</th><th className="pb-2 text-right font-semibold">Qty</th><th className="pb-2 text-right font-semibold">Price</th><th className="pb-2 text-right font-semibold">Discount</th><th className="pb-2 text-right font-semibold">Total</th></tr></thead>
              <tbody>
                {sale.items.map((i) => (
                  <tr key={i.id} className="border-t">
                    <td className="py-2"><div className="font-medium">{i.product_name}</div><div className="font-mono text-xs text-muted-foreground">{i.sku}</div></td>
                    <td className="py-2 text-right tabular">{formatNumber(i.quantity)}{i.returned_quantity > 0 && <div className="text-xs text-warning">{formatNumber(i.returned_quantity)} returned</div>}</td>
                    <td className="py-2 text-right"><Money value={i.unit_price} /></td>
                    <td className="py-2 text-right"><Money value={i.discount_amount} className="text-muted-foreground" /></td>
                    <td className="py-2 text-right"><Money value={i.line_total} className="font-medium" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
        <div className="space-y-4">
          <SectionCard title="Totals">
            <dl className="divide-y">
              <KeyValue label="Subtotal"><Money value={sale.subtotal} /></KeyValue>
              <KeyValue label="Discount"><Money value={-sale.discount_amount} /></KeyValue>
              <KeyValue label="VAT"><Money value={sale.tax_amount} /></KeyValue>
              <KeyValue label="Total"><Money value={sale.total_amount} className="text-base font-semibold" /></KeyValue>
              <KeyValue label="Paid"><Money value={sale.paid_amount} /></KeyValue>
              {sale.change_amount > 0 && <KeyValue label="Change given"><Money value={sale.change_amount} /></KeyValue>}
              {sale.due_amount > 0 && <KeyValue label="Balance due"><Money value={sale.due_amount} className="text-destructive" /></KeyValue>}
              {sale.returned_amount > 0 && <KeyValue label="Returned"><Money value={-sale.returned_amount} /></KeyValue>}
            </dl>
          </SectionCard>
          <SectionCard title="Payments">
            {sale.payments.length === 0 ? <p className="text-sm text-muted-foreground">No payment — full amount on credit.</p> : (
              <ul className="divide-y">{sale.payments.map((p) => <li key={p.id} className="flex items-center justify-between py-2 text-sm"><span>{p.method_name}{(p.transaction_id || p.reference_number) && <span className="ml-2 font-mono text-xs text-muted-foreground">{p.transaction_id ?? p.reference_number}</span>}</span><Money value={p.amount} /></li>)}</ul>
            )}
          </SectionCard>
          {profit !== null && sale.status === "COMPLETED" && (
            <SectionCard title="Margin" description="Visible to users who can see costs"><dl className="divide-y"><KeyValue label="Cost of goods"><Money value={sale.cogs_amount} /></KeyValue><KeyValue label="Gross profit"><Money value={profit} className="font-semibold" signed /></KeyValue></dl></SectionCard>
          )}
        </div>
      </div>

      <ReturnDialog sale={sale} open={returning} onClose={() => setReturning(false)} />
      <ConfirmDialog open={voiding} onOpenChange={setVoiding} title={`Void ${sale.invoice_number}?`} destructive confirmLabel="Void sale"
        description="Stock goes back on the shelf, payments are reversed and the customer’s ledger is corrected. The invoice stays in the records marked VOIDED. This cannot be undone."
        reason={{ label: "Reason for voiding" }} onConfirm={(reason) => voidSale.mutateAsync(reason!)} />
      {print && <PrintPortal>{print === "receipt" ? <Receipt sale={sale} /> : <A4Invoice sale={sale} />}</PrintPortal>}
    </>
  )
}

export function ReturnDialog({ sale, open, onClose }: { sale: Sale; open: boolean; onClose: () => void }) {
  const methods = usePaymentMethods()
  const [qty, setQty] = useState<Record<number, string>>({})
  const [reason, setReason] = useState("")
  const [methodId, setMethodId] = useState("")
  const [reference, setReference] = useState("")
  const [error, setError] = useState<string | null>(null)
  const method = methods.data?.find((m) => String(m.id) === methodId) ?? methods.data?.find((m) => m.method_type === "CASH")
  const ret = useApiMutation(
    (items: { sale_item_id: number; quantity: number }[]) => api.post<SaleReturn>("/sale-returns", { sale_id: sale.id, items, reason, refund_method_id: method?.id, refund_reference: reference || undefined }),
    { success: (r) => `Return ${r.return_number} recorded`, invalidate: [["sales"], ["sale-returns"], ["stock"], ["products"], ["dashboard"], ["cash-session"], ["customers"]], onSuccess: () => { setQty({}); setReason(""); onClose() }, silentError: true },
  )
  async function submit() {
    setError(null)
    const items = sale.items.filter((i) => Number(qty[i.id]) > 0).map((i) => ({ sale_item_id: i.id, quantity: Number(qty[i.id]) }))
    if (items.length === 0) return setError("Enter the quantity to return for at least one item.")
    for (const it of items) {
      const line = sale.items.find((i) => i.id === it.sale_item_id)!
      if (it.quantity > line.quantity - line.returned_quantity) return setError(`Only ${line.quantity - line.returned_quantity} of ${line.product_name} can still be returned.`)
    }
    if (reason.trim().length < 3) return setError("Please enter a reason for the return.")
    if (method?.requires_reference && !reference.trim()) return setError(`${method.name} refunds need a reference.`)
    try { await ret.mutateAsync(items) } catch (e) { setError((e as Error).message) }
  }
  const estimate = sale.items.reduce((s, i) => { const q = Number(qty[i.id]) || 0; return s + (q > 0 ? (i.line_total / i.quantity) * q : 0) }, 0)
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title={`Return items — ${sale.invoice_number}`} description="The original invoice is never edited. A separate return record is created, stock goes back on the shelf and the refund is recorded." size="lg">
      <div className="space-y-4">
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <div className="scroll-thin overflow-x-auto">
          <table className="w-full min-w-[440px] text-sm">
            <thead className="text-xs text-muted-foreground uppercase"><tr className="text-left"><th className="pb-2 font-semibold">Item</th><th className="pb-2 text-right font-semibold">Sold</th><th className="pb-2 text-right font-semibold">Returnable</th><th className="w-28 pb-2 text-right font-semibold">Return qty</th></tr></thead>
            <tbody>
              {sale.items.map((i) => {
                const left = i.quantity - i.returned_quantity
                return (
                  <tr key={i.id} className="border-t">
                    <td className="py-2 font-medium">{i.product_name}</td><td className="py-2 text-right tabular">{formatNumber(i.quantity)}</td><td className="py-2 text-right tabular">{formatNumber(left)}</td>
                    <td className="py-2"><Input type="number" min="0" max={left} step="any" disabled={left <= 0} value={qty[i.id] ?? ""} aria-label={`Return quantity for ${i.product_name}`} className="text-right" onChange={(e) => setQty((q) => ({ ...q, [i.id]: e.target.value }))} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="text-right text-sm text-muted-foreground">Approximate return value: <span className="font-semibold text-foreground">{formatMoney(estimate)}</span> <span className="text-xs">(final amount is calculated by the server)</span></p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Refund method" hint={sale.due_amount > 0 ? "Unpaid balance on this invoice is reduced first" : undefined}>{(p) => <NativeSelect {...p} value={methodId || String(method?.id ?? "")} onChange={(e) => setMethodId(e.target.value)}>{methods.data?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</NativeSelect>}</Field>
          {method?.requires_reference && <Field label="Reference" required>{(p) => <Input {...p} value={reference} onChange={(e) => setReference(e.target.value)} />}</Field>}
        </div>
        <Field label="Reason for return" required>{(p) => <Textarea {...p} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Damaged, wrong item, customer changed mind…" />}</Field>
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose} disabled={ret.isPending}>Cancel</Button><Button onClick={submit} disabled={ret.isPending}>Confirm return</Button></div>
      </div>
    </FormDialog>
  )
}

export function ReturnsList() {
  const [picker, setPicker] = useState(false)
  const [sale, setSale] = useState<Sale | null>(null)
  const { can } = useAuth()
  const { query, data, setPage, search, setSearch } = useTableQuery<SaleReturn>("sale-returns", "/sale-returns")
  async function pick(o: Option | null) { if (o) { setSale(await api.get<Sale>(`/sales/${o.id}`)); setPicker(false) } }
  const findSales = async (q: string): Promise<Option[]> => {
    const r = await api.get<Page<Sale>>("/sales", { search: q, page_size: 15, status: "COMPLETED" })
    return r.items.map((s) => ({ id: s.id, label: s.invoice_number, hint: `${formatMoney(s.total_amount)} · ${s.customer_name ?? "Walk-in"} · ${formatDateTime(s.sale_date)}` }))
  }
  return (
    <>
      <PageHeader title="Sale returns" description="Returns are separate records linked to the original invoice."
        actions={can("sale.return") ? <Button onClick={() => setPicker(true)}><Undo2 className="size-4" /> New return</Button> : undefined} />
      <Toolbar><SearchInput value={search} onChange={setSearch} placeholder="Search return or invoice number…" /></Toolbar>
      <DataTable<SaleReturn>
        page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(r) => r.id}
        empty={{ title: "No returns yet.", description: "Find an invoice and return items from it." }}
        columns={[
          { id: "no", header: "Return no.", cell: (r) => <span className="font-mono text-xs font-medium">{r.return_number}</span> },
          { id: "date", header: "Date", cell: (r) => formatDateTime(r.created_at) },
          { id: "inv", header: "Invoice", cell: (r) => <Link href={`/sales/${r.sale_id}`} className="font-mono text-xs text-primary hover:underline">{r.invoice_number}</Link> },
          { id: "items", header: "Items", cell: (r) => r.items.map((i) => `${i.product_name} ×${formatNumber(i.quantity)}`).join(", "), hideOnMobile: true },
          { id: "amount", header: "Value", align: "right", cell: (r) => <Money value={r.total_amount} className="font-medium" /> },
          { id: "refund", header: "Refunded", align: "right", cell: (r) => (r.refunded_amount > 0 ? <span className="tabular">{formatMoney(r.refunded_amount)} <span className="text-xs text-muted-foreground">{r.refund_method_name}</span></span> : <span className="text-xs text-muted-foreground">Off balance {formatMoney(r.due_reduced)}</span>), hideOnMobile: true },
          { id: "reason", header: "Reason", cell: (r) => <span className="text-muted-foreground">{r.reason}</span>, hideOnMobile: true },
        ]}
      />
      <FormDialog open={picker} onOpenChange={setPicker} title="Find the invoice" description="Search by invoice number, customer name or phone." size="sm">
        <AsyncCombobox value={null} onChange={pick} fetcher={findSales} queryKey="return-sales" placeholder="Search invoices…" clearable={false} />
      </FormDialog>
      {sale && <ReturnDialog sale={sale} open onClose={() => setSale(null)} />}
    </>
  )
}
