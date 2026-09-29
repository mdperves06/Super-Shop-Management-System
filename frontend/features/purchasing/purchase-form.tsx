"use client"

import { Loader2, Trash2 } from "lucide-react"
import { useRouter } from "next/navigation"
import { useMemo, useState } from "react"

import { AsyncCombobox, type Option } from "@/components/shared/combobox"
import { Field, Money, SectionCard } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { api } from "@/lib/api"
import { todayISO } from "@/lib/format"
import { searchProducts, searchSuppliers } from "@/services/lookups"
import type { Product, Purchase } from "@/types/api"

interface Line {
  key: string
  product_id: number
  name: string
  sku: string
  unit: string
  quantity: string
  unit_cost: string
  discount_amount: string
  tax_rate: string
}

const n = (v: string) => (v === "" || Number.isNaN(Number(v)) ? 0 : Number(v))

/** Same arithmetic as the server (per line: gross − discount, then tax). Shown as an estimate; the backend recalculates on save. */
export function estimate(lines: Pick<Line, "quantity" | "unit_cost" | "discount_amount" | "tax_rate">[]) {
  let subtotal = 0, discount = 0, tax = 0
  for (const l of lines) {
    const gross = Math.round(n(l.quantity) * n(l.unit_cost) * 100) / 100
    const d = n(l.discount_amount)
    const t = Math.round((gross - d) * n(l.tax_rate)) / 100
    subtotal += gross; discount += d; tax += t
  }
  return { subtotal, discount, tax, total: subtotal - discount + tax }
}

export function PurchaseForm({ purchase }: { purchase?: Purchase }) {
  const router = useRouter()
  const [supplier, setSupplier] = useState<Option | null>(purchase ? { id: purchase.supplier_id, label: purchase.supplier_name ?? `Supplier #${purchase.supplier_id}` } : null)
  const [orderDate, setOrderDate] = useState(purchase?.order_date ?? todayISO())
  const [expected, setExpected] = useState(purchase?.expected_date ?? "")
  const [notes, setNotes] = useState(purchase?.notes ?? "")
  const [error, setError] = useState<string | null>(null)
  const [lines, setLines] = useState<Line[]>(
    purchase?.items.map((i) => ({ key: `i${i.id}`, product_id: i.product_id, name: i.product_name ?? "", sku: i.sku ?? "", unit: "", quantity: String(i.quantity), unit_cost: String(i.unit_cost), discount_amount: String(i.discount_amount), tax_rate: String(i.tax_rate) })) ?? [],
  )
  const totals = useMemo(() => estimate(lines), [lines])

  async function addProduct(o: Option | null) {
    if (!o) return
    if (lines.some((l) => l.product_id === o.id)) { setError(`${o.label} is already on this order.`); return }
    setError(null)
    const p = await api.get<Product>(`/products/${o.id}`)
    setLines((prev) => [...prev, { key: `p${o.id}-${Date.now()}`, product_id: p.id, name: p.name, sku: p.sku, unit: p.unit.short_name, quantity: "1", unit_cost: p.purchase_price !== null ? String(p.purchase_price) : "", discount_amount: "0", tax_rate: "0" }])
  }
  const patch = (key: string, field: keyof Line, value: string) => setLines((prev) => prev.map((l) => (l.key === key ? { ...l, [field]: value } : l)))

  const save = useApiMutation(
    async (submit: boolean) => {
      const body = {
        supplier_id: supplier!.id, order_date: orderDate, expected_date: expected || null, notes: notes || null,
        items: lines.map((l) => ({ product_id: l.product_id, quantity: n(l.quantity), unit_cost: n(l.unit_cost), discount_amount: n(l.discount_amount), tax_rate: n(l.tax_rate) })),
      }
      if (purchase) {
        const updated = await api.put<Purchase>(`/purchases/${purchase.id}`, body)
        return submit ? api.post<Purchase>(`/purchases/${purchase.id}/submit`) : updated
      }
      return api.post<Purchase>("/purchases", { ...body, submit })
    },
    { success: (p) => `${p.po_number} saved`, invalidate: [["purchases"]], onSuccess: (p) => router.push(`/purchases/${p.id}`), silentError: true },
  )

  async function submit(asSubmit: boolean) {
    setError(null)
    if (!supplier) return setError("Choose a supplier.")
    if (lines.length === 0) return setError("Add at least one product.")
    const bad = lines.find((l) => n(l.quantity) <= 0 || n(l.unit_cost) < 0 || l.unit_cost === "")
    if (bad) return setError(`Check quantity and unit cost for ${bad.name}.`)
    try { await save.mutateAsync(asSubmit) } catch (e) { setError((e as Error).message) }
  }

  return (
    <div className="space-y-4">
      {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
      <SectionCard title="Order details">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Supplier" required>{(p) => <AsyncCombobox id={p.id} value={supplier} onChange={setSupplier} fetcher={searchSuppliers} queryKey="suppliers" placeholder="Choose supplier…" clearable={false} />}</Field>
          <Field label="Order date" required>{(p) => <Input {...p} type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />}</Field>
          <Field label="Expected delivery">{(p) => <Input {...p} type="date" value={expected} min={orderDate} onChange={(e) => setExpected(e.target.value)} />}</Field>
          <Field label="Notes" className="md:col-span-3">{(p) => <Textarea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        </div>
      </SectionCard>

      <SectionCard title="Items" description="Stock is not added until the goods are received.">
        <div className="mb-4 max-w-md">
          <AsyncCombobox value={null} onChange={addProduct} fetcher={searchProducts} queryKey="products" placeholder="+ Add a product…" clearable={false} />
        </div>
        {lines.length === 0 ? (
          <p className="rounded-lg border border-dashed py-10 text-center text-sm text-muted-foreground">No items yet. Search for a product above to add it.</p>
        ) : (
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-xs text-muted-foreground uppercase">
                <tr className="text-left">
                  <th className="pb-2 font-semibold">Product</th><th className="w-24 pb-2 text-right font-semibold">Qty</th><th className="w-28 pb-2 text-right font-semibold">Unit cost</th>
                  <th className="w-28 pb-2 text-right font-semibold">Discount</th><th className="w-20 pb-2 text-right font-semibold">VAT %</th><th className="w-32 pb-2 text-right font-semibold">Line total</th><th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => {
                  const lt = estimate([l]).total
                  return (
                    <tr key={l.key} className="border-t">
                      <td className="py-2 pr-2"><div className="font-medium">{l.name}</div><div className="font-mono text-xs text-muted-foreground">{l.sku}</div></td>
                      {(["quantity", "unit_cost", "discount_amount", "tax_rate"] as const).map((f) => (
                        <td key={f} className="px-1 py-2"><Input type="number" min="0" step={f === "quantity" ? "any" : "0.01"} value={l[f]} aria-label={`${f.replace("_", " ")} for ${l.name}`} className="text-right tabular" onChange={(e) => patch(l.key, f, e.target.value)} /></td>
                      ))}
                      <td className="py-2 pl-2 text-right"><Money value={lt} className="font-medium" /></td>
                      <td className="py-2 pl-1 text-right"><Button variant="ghost" size="icon-sm" aria-label={`Remove ${l.name}`} onClick={() => setLines((prev) => prev.filter((x) => x.key !== l.key))}><Trash2 className="size-4" /></Button></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-4 ml-auto w-full max-w-xs space-y-1 text-sm">
          <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><Money value={totals.subtotal} /></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Discount</span><Money value={-totals.discount} /></div>
          <div className="flex justify-between"><span className="text-muted-foreground">VAT</span><Money value={totals.tax} /></div>
          <div className="flex justify-between border-t pt-2 text-base font-semibold"><span>Total (estimate)</span><Money value={totals.total} /></div>
          <p className="text-xs text-muted-foreground">Final amounts are calculated by the server when you save.</p>
        </div>
      </SectionCard>

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => router.back()} disabled={save.isPending}>Cancel</Button>
        <Button variant="secondary" onClick={() => submit(false)} disabled={save.isPending}>{save.isPending && <Loader2 className="size-4 animate-spin" />}Save as draft</Button>
        <Button onClick={() => submit(true)} disabled={save.isPending}>Save & submit</Button>
      </div>
    </div>
  )
}
