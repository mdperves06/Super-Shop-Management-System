"use client"

import { useState } from "react"

import { DataTable, Toolbar } from "@/components/shared/data-table"
import { FormDialog, SubmitRow } from "@/components/shared/dialogs"
import { DateRangeFilter, type DateRange } from "@/components/shared/filters"
import { Field, Money, NativeSelect, StatusBadge } from "@/components/shared/ui-parts"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api } from "@/lib/api"
import { formatDateTime, formatMoney } from "@/lib/format"
import { usePaymentMethods } from "@/services/lookups"
import type { LedgerRow } from "@/types/api"

const TXN_TONE: Record<string, "success" | "danger" | "warning" | "info" | "neutral"> = {
  SALE: "info", PURCHASE: "info", PAYMENT: "success", RETURN: "warning", VOID: "danger", ADJUSTMENT: "neutral", OPENING: "neutral",
}

/** Ledger for a customer or supplier. Positive = balance grows, negative = balance shrinks. */
export function LedgerTable({ basePath, id, owed }: { basePath: "/customers" | "/suppliers"; id: number; owed: string }) {
  const [range, setRange] = useState<DateRange>({ start: "", end: "" })
  const ok = !!range.start && !!range.end
  const { query, data, setPage } = useTableQuery<LedgerRow>(`ledger-${basePath}-${id}`, `${basePath}/${id}/ledger`, { filters: { start: ok ? range.start : undefined, end: ok ? range.end : undefined }, pageSize: 25 })
  return (
    <>
      <Toolbar><DateRangeFilter value={range} onChange={setRange} /></Toolbar>
      <DataTable<LedgerRow>
        page={data} isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(r) => r.id}
        empty={{ title: "No ledger entries yet.", description: "Sales, purchases, payments and returns appear here as they happen." }}
        columns={[
          { id: "date", header: "Date", cell: (r) => <span className="whitespace-nowrap">{formatDateTime(r.created_at)}</span> },
          { id: "type", header: "Type", cell: (r) => <StatusBadge status={r.txn_type} tone={TXN_TONE[r.txn_type] ?? "neutral"} /> },
          { id: "ref", header: "Reference", cell: (r) => <span className="font-mono text-xs">{r.reference_number ?? "—"}</span> },
          { id: "notes", header: "Notes", cell: (r) => <span className="text-muted-foreground">{r.notes ?? ""}</span>, hideOnMobile: true },
          { id: "amount", header: "Amount", align: "right", cell: (r) => <span className={`tabular font-medium ${r.amount < 0 ? "text-success" : ""}`}>{r.amount > 0 ? "+" : ""}{formatMoney(r.amount)}</span> },
          { id: "balance", header: owed, align: "right", cell: (r) => <Money value={r.balance_after} className="font-semibold" /> },
        ]}
      />
    </>
  )
}

export function PaymentDialog({ open, onClose, basePath, id, name, balance, purchaseId }: {
  open: boolean; onClose: () => void; basePath: "/customers" | "/suppliers"; id: number; name: string; balance: number; purchaseId?: number
}) {
  const methods = usePaymentMethods()
  const [amount, setAmount] = useState("")
  const [methodId, setMethodId] = useState("")
  const [reference, setReference] = useState("")
  const [notes, setNotes] = useState("")
  const [error, setError] = useState<string | null>(null)
  const method = methods.data?.find((m) => String(m.id) === methodId) ?? methods.data?.[0]
  const pay = useApiMutation(
    () => api.post(`${basePath}/${id}/payments`, { amount: Number(amount), payment_method_id: method!.id, reference_number: reference || undefined, notes: notes || undefined, purchase_id: purchaseId }),
    { success: `Payment of ${formatMoney(Number(amount))} recorded`, invalidate: [[basePath.slice(1)], ["ledger-" + basePath], ["purchases"], ["dashboard"], ["cash-session"]], onSuccess: () => { setAmount(""); setReference(""); setNotes(""); onClose() }, silentError: true },
  )
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const a = Number(amount)
    if (!(a > 0)) return setError("Enter an amount greater than zero.")
    if (a > balance) return setError(`The amount exceeds the outstanding balance of ${formatMoney(balance)}.`)
    if (method?.requires_reference && !reference.trim()) return setError(`${method.name} payments need a reference / transaction ID.`)
    try { await pay.mutateAsync() } catch (err) { setError((err as Error).message) }
  }
  const verb = basePath === "/suppliers" ? "Pay" : "Receive payment from"
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title={`${verb} ${name}`} description={`Outstanding balance: ${formatMoney(balance)}`} size="sm">
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <Field label="Amount" required>{(p) => (
          <div className="flex gap-2">
            <Input {...p} type="number" min="0" step="0.01" inputMode="decimal" autoFocus value={amount} onChange={(e) => setAmount(e.target.value)} />
            <button type="button" className="rounded-lg border px-3 text-xs hover:bg-muted" onClick={() => setAmount(String(balance))}>Full</button>
          </div>
        )}</Field>
        <Field label="Payment method" required>{(p) => <NativeSelect {...p} value={methodId || String(method?.id ?? "")} onChange={(e) => setMethodId(e.target.value)}>{methods.data?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</NativeSelect>}</Field>
        {method?.requires_reference && <Field label="Reference / transaction ID" required>{(p) => <Input {...p} value={reference} onChange={(e) => setReference(e.target.value)} />}</Field>}
        <Field label="Notes">{(p) => <Textarea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <SubmitRow onCancel={onClose} submitting={pay.isPending} submitLabel="Record payment" />
      </form>
    </FormDialog>
  )
}


export function AdjustBalanceDialog({ open, onClose, basePath, id, name, balance }: { open: boolean; onClose: () => void; basePath: "/customers" | "/suppliers"; id: number; name: string; balance: number }) {
  const [amount, setAmount] = useState("")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const adjust = useApiMutation(
    () => api.post(`${basePath}/${id}/adjustments`, { amount: Number(amount), reason }),
    { success: "Balance adjusted", invalidate: [[basePath.slice(1)], ["ledger-" + basePath], ["dashboard"]], onSuccess: () => { setAmount(""); setReason(""); onClose() }, silentError: true },
  )
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!Number(amount)) return setError("Enter a non-zero amount (negative to reduce the balance).")
    if (reason.trim().length < 3) return setError("A reason is required.")
    try { await adjust.mutateAsync() } catch (err) { setError((err as Error).message) }
  }
  const owes = basePath === "/suppliers" ? "what you owe them" : "what they owe you"
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title={`Adjust balance — ${name}`} description={`Current balance ${formatMoney(balance)}. A positive amount increases ${owes}; a negative amount reduces it. Recorded in the ledger and audit log.`} size="sm">
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <Field label="Amount (+/−)" required>{(p) => <Input {...p} type="number" step="0.01" autoFocus value={amount} onChange={(e) => setAmount(e.target.value)} />}</Field>
        <Field label="Reason" required>{(p) => <Textarea {...p} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        <SubmitRow onCancel={onClose} submitting={adjust.isPending} submitLabel="Apply adjustment" />
      </form>
    </FormDialog>
  )
}
