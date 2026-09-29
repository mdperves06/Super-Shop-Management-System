"use client"

import { useQuery } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"

import { AsyncCombobox, type Option } from "@/components/shared/combobox"
import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { FormDialog } from "@/components/shared/dialogs"
import { Can, Field, Money, NativeSelect, PageHeader } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api } from "@/lib/api"
import { formatDate, formatNumber } from "@/lib/format"
import { searchProducts, searchSuppliers } from "@/services/lookups"
import type { Batch, Page, PurchaseReturn } from "@/types/api"

export function PurchaseReturnsPage() {
  const [open, setOpen] = useState(false)
  const { query, data, setPage, search, setSearch } = useTableQuery<PurchaseReturn>("purchase-returns", "/purchase-returns")
  return (
    <>
      <PageHeader title="Purchase returns" description="Goods sent back to suppliers reduce stock and what you owe them."
        actions={<Can perm="purchase.return"><Button onClick={() => setOpen(true)}><Plus className="size-4" /> New return</Button></Can>} />
      <Toolbar><SearchInput value={search} onChange={setSearch} placeholder="Search return number or supplier…" /></Toolbar>
      <DataTable<PurchaseReturn>
        page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(r) => r.id}
        empty={{ title: "No purchase returns yet.", description: "Return damaged or wrong goods to a supplier to adjust stock and their balance." }}
        columns={[
          { id: "no", header: "Return no.", cell: (r) => <span className="font-mono text-xs font-medium">{r.return_number}</span> },
          { id: "date", header: "Date", cell: (r) => formatDate(r.return_date) },
          { id: "supplier", header: "Supplier", cell: (r) => <span className="font-medium">{r.supplier_name}</span> },
          { id: "items", header: "Items", cell: (r) => r.items.map((i) => `${i.product_name} ×${formatNumber(i.quantity)}`).join(", "), hideOnMobile: true },
          { id: "amount", header: "Credit", align: "right", cell: (r) => <Money value={r.total_amount} className="font-medium" /> },
          { id: "reason", header: "Reason", cell: (r) => <span className="text-muted-foreground">{r.reason}</span>, hideOnMobile: true },
        ]}
      />
      <ReturnDialog open={open} onClose={() => setOpen(false)} />
    </>
  )
}

function ReturnDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [supplier, setSupplier] = useState<Option | null>(null)
  const [product, setProduct] = useState<Option | null>(null)
  const [batchId, setBatchId] = useState("")
  const [qty, setQty] = useState("1")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const batches = useQuery({
    queryKey: ["batches-for-return", product?.id],
    queryFn: () => api.get<Page<Batch>>("/inventory/batches", { product_id: product!.id, page_size: 100 }),
    enabled: !!product,
  })
  const save = useApiMutation(
    () => api.post("/purchase-returns", { supplier_id: supplier!.id, reason, items: [{ product_id: product!.id, batch_id: Number(batchId), quantity: Number(qty) }] }),
    { success: "Return recorded", invalidate: [["purchase-returns"], ["stock"], ["suppliers"], ["products"]], onSuccess: () => { setSupplier(null); setProduct(null); setBatchId(""); setQty("1"); setReason(""); onClose() }, silentError: true },
  )
  async function submit() {
    setError(null)
    if (!supplier) return setError("Choose the supplier.")
    if (!product || !batchId) return setError("Choose the product and the batch you are returning.")
    if (!(Number(qty) > 0)) return setError("Enter a quantity greater than zero.")
    if (reason.trim().length < 3) return setError("A reason is required.")
    try { await save.mutateAsync() } catch (e) { setError((e as Error).message) }
  }
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title="Return goods to supplier" description="Pick the exact batch. Stock decreases and the supplier’s balance is credited." size="md">
      <div className="space-y-4">
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <Field label="Supplier" required>{(p) => <AsyncCombobox id={p.id} value={supplier} onChange={setSupplier} fetcher={searchSuppliers} queryKey="suppliers" clearable={false} placeholder="Choose supplier…" />}</Field>
        <Field label="Product" required>{(p) => <AsyncCombobox id={p.id} value={product} onChange={(o) => { setProduct(o); setBatchId("") }} fetcher={searchProducts} queryKey="products" clearable={false} placeholder="Search product…" />}</Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Batch" required>
            {(p) => (
              <NativeSelect {...p} value={batchId} onChange={(e) => setBatchId(e.target.value)} disabled={!product}>
                <option value="">{product ? (batches.isLoading ? "Loading…" : "Select batch…") : "Choose a product first"}</option>
                {batches.data?.items.map((b) => <option key={b.id} value={b.id}>{b.batch_number} — {formatNumber(b.quantity_remaining)} left{b.expiry_date ? ` · exp ${formatDate(b.expiry_date)}` : ""}</option>)}
              </NativeSelect>
            )}
          </Field>
          <Field label="Quantity" required>{(p) => <Input {...p} type="number" min="0" step="any" value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
        </div>
        <Field label="Reason" required>{(p) => <Textarea {...p} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Damaged on arrival, wrong item, expired…" />}</Field>
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={submit} disabled={save.isPending}>Record return</Button></div>
      </div>
    </FormDialog>
  )
}
