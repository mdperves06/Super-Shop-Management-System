"use client"

import { Banknote, CreditCard, Landmark, Loader2, Plus, Smartphone, Trash2 } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { FormDialog } from "@/components/shared/dialogs"
import { NativeSelect } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { CartPayload } from "@/features/pos/types"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatMoney } from "@/lib/format"
import { usePaymentMethods } from "@/services/lookups"
import type { PaymentMethod, Sale } from "@/types/api"

interface PayLine {
  key: number
  methodId: number
  amount: string
  reference: string
}

const ICON: Record<string, typeof Banknote> = { CASH: Banknote, CARD: CreditCard, MOBILE: Smartphone, BANK: Landmark, OTHER: Landmark }
const round2 = (n: number) => Math.round(n * 100) / 100

export function PaymentDialog({ open, onClose, total, payload, customerName, hasCustomer, creditAvailable, onDone }: {
  open: boolean
  onClose: () => void
  total: number
  payload: CartPayload
  customerName: string | null
  hasCustomer: boolean
  creditAvailable: number | null
  onDone: (sale: Sale) => void
}) {
  const { can } = useAuth()
  const methods = usePaymentMethods()
  const [lines, setLines] = useState<PayLine[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const clientRef = useRef<string>("")
  const amountRef = useRef<HTMLInputElement>(null)
  const seq = useRef(1)
  const cash = methods.data?.find((m) => m.method_type === "CASH")

  // fresh idempotency key each time the dialog opens; reused on retries so a double-click cannot create two invoices
  useEffect(() => {
    if (open && cash) {
      clientRef.current = crypto.randomUUID()
      setLines([{ key: seq.current++, methodId: cash.id, amount: "", reference: "" }]) // eslint-disable-line react-hooks/set-state-in-effect
      setError(null)
      setTimeout(() => amountRef.current?.focus(), 50)
    }
  }, [open, cash])

  const byId = useMemo(() => new Map<number, PaymentMethod>((methods.data ?? []).map((m) => [m.id, m])), [methods.data])
  const calc = useMemo(() => {
    let cashTendered = 0, other = 0
    for (const l of lines) {
      const a = Number(l.amount) || 0
      if (byId.get(l.methodId)?.method_type === "CASH") cashTendered += a
      else other += a
    }
    const cashNeeded = Math.max(total - other, 0)
    const change = round2(Math.max(cashTendered - cashNeeded, 0))
    const applied = round2(Math.min(cashTendered, cashNeeded) + other)
    const due = round2(Math.max(total - applied, 0))
    return { cashTendered, other, change, applied, due, overOther: other > total + 0.001 }
  }, [lines, byId, total])

  const creditOk = calc.due === 0 || (hasCustomer && can("sale.credit") && (creditAvailable ?? 0) + 0.001 >= calc.due)
  const creditMessage = calc.due > 0
    ? !hasCustomer ? "Payment is less than the total. Select a customer to sell on credit, or collect the full amount."
      : !can("sale.credit") ? "You are not allowed to sell on credit. Collect the full amount or ask a manager."
      : (creditAvailable ?? 0) + 0.001 < calc.due ? `Credit limit exceeded — ${customerName} has ${formatMoney(creditAvailable ?? 0)} available.` : null
    : null

  const setLine = (key: number, patch: Partial<PayLine>) => setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)))
  const remainingFor = (key: number) => {
    const others = lines.filter((l) => l.key !== key).reduce((s, l) => s + (Number(l.amount) || 0), 0)
    return Math.max(round2(total - others), 0)
  }

  async function confirm() {
    setError(null)
    if (calc.overOther) return setError("Card / mobile / bank payments cannot exceed the total.")
    if (!creditOk) return setError(creditMessage)
    for (const l of lines) {
      const m = byId.get(l.methodId)
      if ((Number(l.amount) || 0) > 0 && m?.requires_reference && !l.reference.trim()) return setError(`${m.name} needs a reference / transaction ID.`)
    }
    const payments = lines.filter((l) => Number(l.amount) > 0).map((l) => ({ payment_method_id: l.methodId, amount: Number(l.amount), reference_number: byId.get(l.methodId)?.requires_reference ? l.reference.trim() : undefined, transaction_id: byId.get(l.methodId)?.method_type === "MOBILE" ? l.reference.trim() || undefined : undefined }))
    setBusy(true)
    try {
      const sale = await api.post<Sale>("/sales", { ...payload, payments, client_ref: clientRef.current })
      onDone(sale)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const quick = [100, 200, 500, 1000, 2000, 5000]
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && !busy && onClose()} title="Take payment" size="lg">
      <div className="space-y-4">
        <div className="flex items-end justify-between rounded-xl bg-primary/8 px-4 py-3">
          <span className="text-sm text-muted-foreground">Amount due{customerName ? ` · ${customerName}` : ""}</span>
          <span className="text-3xl font-bold tabular">{formatMoney(total)}</span>
        </div>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}

        <div className="space-y-3">
          {lines.map((l, idx) => {
            const m = byId.get(l.methodId)
            const Icon = ICON[m?.method_type ?? "OTHER"] ?? Banknote
            return (
              <div key={l.key} className="rounded-xl border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Icon className="size-5 text-muted-foreground" aria-hidden />
                  <NativeSelect aria-label={`Payment method ${idx + 1}`} value={l.methodId} onChange={(e) => setLine(l.key, { methodId: Number(e.target.value), reference: "" })} className="h-11 w-44 text-base">
                    {methods.data?.map((mm) => <option key={mm.id} value={mm.id}>{mm.name}</option>)}
                  </NativeSelect>
                  <Input ref={idx === 0 ? amountRef : undefined} type="number" min="0" step="0.01" inputMode="decimal" aria-label={`Amount ${idx + 1}`} placeholder="0.00" value={l.amount}
                    onChange={(e) => setLine(l.key, { amount: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void confirm() } }}
                    className="h-11 min-w-32 flex-1 text-right text-lg font-semibold tabular" />
                  <Button variant="outline" className="h-11" onClick={() => setLine(l.key, { amount: String(remainingFor(l.key)) })}>Exact</Button>
                  {lines.length > 1 && <Button variant="ghost" size="icon" aria-label="Remove payment line" onClick={() => setLines((prev) => prev.filter((x) => x.key !== l.key))}><Trash2 className="size-4" /></Button>}
                </div>
                {m?.requires_reference && <Input className="mt-2" aria-label={`${m.name} reference`} placeholder={m.method_type === "MOBILE" ? "Transaction ID (TrxID)" : "Reference / approval code"} value={l.reference} onChange={(e) => setLine(l.key, { reference: e.target.value })} />}
                {m?.method_type === "CASH" && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {quick.map((q) => <button key={q} type="button" className="rounded-md border px-2.5 py-1 text-xs hover:bg-muted" onClick={() => setLine(l.key, { amount: String((Number(l.amount) || 0) + q) })}>+{q}</button>)}
                    <button type="button" className="rounded-md border px-2.5 py-1 text-xs hover:bg-muted" onClick={() => setLine(l.key, { amount: "" })}>Clear</button>
                  </div>
                )}
              </div>
            )
          })}
          <Button variant="outline" onClick={() => setLines((prev) => [...prev, { key: seq.current++, methodId: methods.data?.find((m) => m.method_type === "MOBILE")?.id ?? cash!.id, amount: String(Math.max(round2(total - calc.applied), 0) || ""), reference: "" }])}>
            <Plus className="size-4" /> Split payment
          </Button>
        </div>

        <dl className="grid grid-cols-3 gap-2 rounded-xl bg-muted/60 p-3 text-center">
          <div><dt className="text-xs text-muted-foreground">Received</dt><dd className="text-lg font-semibold tabular">{formatMoney(calc.cashTendered + calc.other)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Change</dt><dd className={`text-lg font-semibold tabular ${calc.change > 0 ? "text-success" : ""}`}>{formatMoney(calc.change)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">On credit</dt><dd className={`text-lg font-semibold tabular ${calc.due > 0 ? "text-destructive" : ""}`}>{formatMoney(calc.due)}</dd></div>
        </dl>
        {creditMessage && <p className="text-sm text-warning" role="status">{creditMessage}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="outline" size="lg" onClick={onClose} disabled={busy}>Back</Button>
          <Button size="lg" className="min-w-44" onClick={confirm} disabled={busy || !creditOk || calc.overOther || (calc.applied === 0 && !(calc.due > 0 && creditOk))}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            {calc.due === 0 ? "Complete sale"
              : calc.applied === 0 ? (creditOk ? "Sell fully on credit" : "Enter payment")
              : creditOk ? `Complete sale · ${formatMoney(calc.due)} on credit` : `Short by ${formatMoney(calc.due)}`}
          </Button>
        </div>
      </div>
    </FormDialog>
  )
}
