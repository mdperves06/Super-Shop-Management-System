"use client"

import { useQuery } from "@tanstack/react-query"
import { Check, FileText, PackageCheck, PackageOpen, X } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { ConfirmDialog, FormDialog } from "@/components/shared/dialogs"
import { KeyValue, Money, PageHeader, PageLoading, SectionCard, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { PurchaseForm } from "@/features/purchasing/purchase-form"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { api, errorMessage, openFile } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDate, formatDateTime, formatNumber, todayISO } from "@/lib/format"
import type { GoodsReceipt, Page, Purchase } from "@/types/api"

export function PurchaseDetail({ id }: { id: number }) {
  const { can } = useAuth()
  const { data: po, isLoading, error } = useQuery({ queryKey: ["purchases", "detail", id], queryFn: () => api.get<Purchase>(`/purchases/${id}`) })
  const receipts = useQuery({ queryKey: ["goods-receipts", id], queryFn: () => api.get<Page<GoodsReceipt>>("/goods-receipts", { purchase_id: id, page_size: 50 }), enabled: !!po })
  const [receiveOpen, setReceiveOpen] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)
  const refresh = [["purchases"], ["goods-receipts"], ["stock"], ["suppliers"], ["products"], ["dashboard"]]
  const submit = useApiMutation(() => api.post(`/purchases/${id}/submit`), { success: "Submitted for approval", invalidate: refresh })
  const approve = useApiMutation(() => api.post(`/purchases/${id}/approve`), { success: "Purchase order approved", invalidate: refresh })
  const cancel = useApiMutation((reason: string) => api.post(`/purchases/${id}/cancel`, { reason }), { success: "Purchase order cancelled", invalidate: refresh })

  if (isLoading) return <PageLoading />
  if (error || !po) return <p className="mt-10 text-center text-sm text-muted-foreground" role="alert">{errorMessage(error ?? new Error("Purchase order not found"))}</p>

  if (po.status === "DRAFT" && can("purchase.create")) {
    return (
      <>
        <PageHeader back={{ href: "/purchases", label: "Purchase orders" }} title={`Edit ${po.po_number}`} description="Draft — nothing has been ordered yet." />
        <PurchaseForm purchase={po} />
      </>
    )
  }

  const canReceive = can("purchase.receive") && (po.status === "APPROVED" || po.status === "PARTIALLY_RECEIVED")
  return (
    <>
      <PageHeader
        back={{ href: "/purchases", label: "Purchase orders" }}
        title={<span className="flex items-center gap-3">{po.po_number} <StatusBadge status={po.status} /></span>}
        description={`${po.supplier_name} · ordered ${formatDate(po.order_date)}${po.expected_date ? ` · expected ${formatDate(po.expected_date)}` : ""}`}
        actions={
          <>
            <Button variant="outline" onClick={() => void openFile(`/documents/purchases/${po.id}/invoice.pdf`)}><FileText className="size-4" /> PDF</Button>
            {po.status === "DRAFT" && can("purchase.create") && <Button variant="outline" onClick={() => submit.mutate()}>Submit</Button>}
            {(po.status === "PENDING" || po.status === "DRAFT") && can("purchase.approve") && <Button onClick={() => approve.mutate()} disabled={approve.isPending}><Check className="size-4" /> Approve</Button>}
            {canReceive && <Button onClick={() => setReceiveOpen(true)}><PackageCheck className="size-4" /> Receive stock</Button>}
            {["DRAFT", "PENDING", "APPROVED"].includes(po.status) && can("purchase.cancel") && <Button variant="destructive" onClick={() => setCancelOpen(true)}><X className="size-4" /> Cancel</Button>}
            {po.status !== "CANCELLED" && can("supplier.payment") && po.received_value > po.paid_amount && <Button variant="outline" render={<Link href={`/suppliers/${po.supplier_id}?pay=1&po=${po.id}`} />}>Pay supplier</Button>}
          </>
        }
      />
      {po.status === "CANCELLED" && po.cancelled_reason && <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">Cancelled: {po.cancelled_reason}</div>}

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <SectionCard title="Items">
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-xs text-muted-foreground uppercase"><tr className="text-left"><th className="pb-2 font-semibold">Product</th><th className="pb-2 text-right font-semibold">Ordered</th><th className="pb-2 text-right font-semibold">Received</th><th className="pb-2 text-right font-semibold">Unit cost</th><th className="pb-2 text-right font-semibold">Total</th></tr></thead>
              <tbody>
                {po.items.map((i) => (
                  <tr key={i.id} className="border-t">
                    <td className="py-2"><div className="font-medium">{i.product_name}</div><div className="font-mono text-xs text-muted-foreground">{i.sku}</div></td>
                    <td className="py-2 text-right tabular">{formatNumber(i.quantity)}</td>
                    <td className="py-2 text-right tabular"><span className={i.received_quantity >= i.quantity ? "text-success" : i.received_quantity > 0 ? "text-warning" : "text-muted-foreground"}>{formatNumber(i.received_quantity)}</span></td>
                    <td className="py-2 text-right"><Money value={i.unit_cost} /></td>
                    <td className="py-2 text-right"><Money value={i.line_total} className="font-medium" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
        <div className="space-y-4">
          <SectionCard title="Summary">
            <dl className="divide-y">
              <KeyValue label="Subtotal"><Money value={po.subtotal} /></KeyValue>
              <KeyValue label="Discount"><Money value={-po.discount_amount} /></KeyValue>
              <KeyValue label="VAT"><Money value={po.tax_amount} /></KeyValue>
              <KeyValue label="Total"><Money value={po.total_amount} className="text-base font-semibold" /></KeyValue>
              <KeyValue label="Received value"><Money value={po.received_value} /></KeyValue>
              <KeyValue label="Paid to supplier"><Money value={po.paid_amount} /></KeyValue>
            </dl>
          </SectionCard>
          {po.notes && <SectionCard title="Notes"><p className="text-sm whitespace-pre-wrap">{po.notes}</p></SectionCard>}
        </div>
      </div>

      <SectionCard className="mt-4" title="Goods receipts" description="Each receipt created stock batches and added to the supplier payable.">
        {(receipts.data?.items.length ?? 0) === 0 ? (
          <p className="flex items-center gap-2 py-4 text-sm text-muted-foreground"><PackageOpen className="size-4" /> Nothing has been received yet.</p>
        ) : (
          <ul className="divide-y">{receipts.data!.items.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 py-2 text-sm"><span><span className="font-mono text-xs font-medium">{r.grn_number}</span> <span className="text-muted-foreground">· {formatDateTime(r.received_at)} · {r.received_by_name}</span></span><Money value={r.value} className="font-medium" /></li>
          ))}</ul>
        )}
      </SectionCard>

      <ReceiveDialog po={po} open={receiveOpen} onClose={() => setReceiveOpen(false)} />
      <ConfirmDialog open={cancelOpen} onOpenChange={setCancelOpen} title={`Cancel ${po.po_number}?`} description="A cancelled order cannot be reopened. It stays in the records." confirmLabel="Cancel order" destructive reason={{ label: "Reason for cancelling" }} onConfirm={(reason) => cancel.mutateAsync(reason!)} />
    </>
  )
}

function ReceiveDialog({ po, open, onClose }: { po: Purchase; open: boolean; onClose: () => void }) {
  const outstanding = po.items.filter((i) => i.quantity - i.received_quantity > 0)
  const [rows, setRows] = useState<Record<number, { qty: string; batch: string; mfg: string; expiry: string }>>({})
  const [notes, setNotes] = useState("")
  const [error, setError] = useState<string | null>(null)
  const get = (id: number, def: number) => rows[id] ?? { qty: String(def), batch: "", mfg: "", expiry: "" }
  const set = (id: number, def: number, patch: Partial<{ qty: string; batch: string; mfg: string; expiry: string }>) => setRows((r) => ({ ...r, [id]: { ...get(id, def), ...patch } }))

  const receive = useApiMutation(
    (items: { item_id: number; quantity: number; batch_number?: string; manufacturing_date?: string; expiry_date?: string }[]) => api.post(`/purchases/${po.id}/receive`, { items, notes: notes || undefined }),
    { success: "Stock received", invalidate: [["purchases"], ["goods-receipts"], ["stock"], ["suppliers"], ["products"], ["dashboard"], ["low-stock"]], onSuccess: onClose, silentError: true },
  )

  async function submit() {
    setError(null)
    const items = []
    for (const i of outstanding) {
      const r = get(i.id, i.quantity - i.received_quantity)
      const qty = Number(r.qty)
      if (!qty) continue
      if (qty < 0 || qty > i.quantity - i.received_quantity) return setError(`${i.product_name}: quantity must be between 0 and ${i.quantity - i.received_quantity}.`)
      if (i.track_expiry && !r.expiry) return setError(`${i.product_name} tracks expiry — enter the expiry date.`)
      items.push({ item_id: i.id, quantity: qty, batch_number: r.batch || undefined, manufacturing_date: r.mfg || undefined, expiry_date: r.expiry || undefined })
    }
    if (items.length === 0) return setError("Enter a quantity for at least one item.")
    try { await receive.mutateAsync(items) } catch (e) { setError((e as Error).message) }
  }

  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title={`Receive stock — ${po.po_number}`} description="Enter what actually arrived. Partial deliveries are fine — receive the rest later." size="xl">
      <div className="space-y-4">
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <div className="scroll-thin overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-xs text-muted-foreground uppercase"><tr className="text-left"><th className="pb-2 font-semibold">Product</th><th className="w-24 pb-2 text-right font-semibold">Receive</th><th className="w-36 pb-2 font-semibold">Batch no.</th><th className="w-36 pb-2 font-semibold">Mfg date</th><th className="w-40 pb-2 font-semibold">Expiry</th></tr></thead>
            <tbody>
              {outstanding.map((i) => {
                const out = i.quantity - i.received_quantity
                const r = get(i.id, out)
                return (
                  <tr key={i.id} className="border-t align-top">
                    <td className="py-2 pr-2"><div className="font-medium">{i.product_name}</div><div className="text-xs text-muted-foreground">{formatNumber(out)} outstanding of {formatNumber(i.quantity)}</div></td>
                    <td className="px-1 py-2"><Input type="number" min="0" max={out} step="any" value={r.qty} aria-label={`Quantity received for ${i.product_name}`} className="text-right" onChange={(e) => set(i.id, out, { qty: e.target.value })} /></td>
                    <td className="px-1 py-2"><Input value={r.batch} placeholder="auto" aria-label={`Batch number for ${i.product_name}`} onChange={(e) => set(i.id, out, { batch: e.target.value })} /></td>
                    <td className="px-1 py-2"><Input type="date" value={r.mfg} aria-label={`Manufacturing date for ${i.product_name}`} onChange={(e) => set(i.id, out, { mfg: e.target.value })} max={todayISO()} /></td>
                    <td className="px-1 py-2"><Input type="date" value={r.expiry} aria-label={`Expiry date for ${i.product_name}`} aria-required={i.track_expiry} onChange={(e) => set(i.id, out, { expiry: e.target.value })} />{i.track_expiry && <span className="text-[11px] text-muted-foreground">Required</span>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Delivery note / remarks (optional)" aria-label="Receipt notes" />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={receive.isPending}>Cancel</Button>
          <Button onClick={submit} disabled={receive.isPending}>Confirm receipt</Button>
        </div>
      </div>
    </FormDialog>
  )
}
