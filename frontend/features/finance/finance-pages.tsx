"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQuery } from "@tanstack/react-query"
import { Ban, Landmark, Paperclip, Plus } from "lucide-react"
import { useRef, useState } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { ConfirmDialog, FormDialog, SubmitRow } from "@/components/shared/dialogs"
import { DateRangeFilter, type DateRange } from "@/components/shared/filters"
import { Can, Field, KeyValue, Money, NativeSelect, PageHeader, PageLoading, SectionCard, StatCard, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { OpenRegisterCard, useCurrentSession } from "@/features/pos/register-gate"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api, downloadFile } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDate, formatDateTime, formatMoney, humanize, todayISO } from "@/lib/format"
import { optionalNumber, usePaymentMethods } from "@/services/lookups"
import type { CashSession, Expense, ExpenseCategory } from "@/types/api"

/* -------------------------------- expenses -------------------------------- */

const schema = z.object({
  category_id: z.number({ error: "Choose a category" }),
  amount: z.number({ error: "Enter an amount" }).positive("Must be greater than zero").max(999999999),
  payment_method_id: z.number({ error: "Choose a payment method" }),
  expense_date: z.string().min(1, "Choose a date"),
  description: z.string().max(1000).optional(),
})
type Values = z.infer<typeof schema>

function ExpenseDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const cats = useQuery({ queryKey: ["expense-categories"], queryFn: () => api.get<ExpenseCategory[]>("/expense-categories"), staleTime: 60_000 })
  const methods = usePaymentMethods()
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const { register, handleSubmit, reset, formState: { errors } } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { expense_date: todayISO(), description: "" } })
  const save = useApiMutation(
    async (v: Values) => {
      const e = await api.post<Expense>("/expenses", { ...v, description: v.description || null })
      if (file) { const f = new FormData(); f.append("file", file); await api.upload(`/expenses/${e.id}/attachment`, f) }
      return e
    },
    { success: (e) => `Expense ${e.expense_number} recorded`, invalidate: [["expenses"], ["cash-session"], ["dashboard"]], onSuccess: () => { reset({ expense_date: todayISO(), description: "" }); setFile(null); onClose() }, silentError: true },
  )
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title="Record expense" description="Cash expenses are deducted from your open register session." >
      <form onSubmit={handleSubmit(async (v) => { setServerError(null); try { await save.mutateAsync(v) } catch (e) { setServerError((e as Error).message) } })} className="space-y-4" noValidate>
        {serverError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{serverError}</div>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Category" required error={errors.category_id?.message}>{(p) => <NativeSelect {...p} {...register("category_id", { setValueAs: optionalNumber })}><option value="">Select…</option>{cats.data?.filter((c) => c.is_active).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect>}</Field>
          <Field label="Amount (৳)" required error={errors.amount?.message}>{(p) => <Input {...p} type="number" step="0.01" min="0" inputMode="decimal" {...register("amount", { setValueAs: optionalNumber })} />}</Field>
          <Field label="Paid with" required error={errors.payment_method_id?.message}>{(p) => <NativeSelect {...p} {...register("payment_method_id", { setValueAs: optionalNumber })}><option value="">Select…</option>{methods.data?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</NativeSelect>}</Field>
          <Field label="Date" required error={errors.expense_date?.message}>{(p) => <Input {...p} type="date" max={todayISO()} {...register("expense_date")} />}</Field>
        </div>
        <Field label="Description">{(p) => <Textarea {...p} rows={2} {...register("description")} />}</Field>
        <div>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,application/pdf" className="sr-only" aria-label="Receipt attachment" onChange={(e) => { const f = e.target.files?.[0]; if (f && f.size > 5 * 1024 * 1024) { toast.error("Attachment must be smaller than 5 MB"); return } setFile(f ?? null) }} />
          <Button type="button" variant="outline" onClick={() => fileRef.current?.click()}><Paperclip className="size-4" /> {file ? file.name : "Attach receipt (image or PDF)"}</Button>
        </div>
        <SubmitRow onCancel={onClose} submitting={save.isPending} submitLabel="Record expense" />
      </form>
    </FormDialog>
  )
}

export function ExpensesPage() {
  const { can } = useAuth()
  const cats = useQuery({ queryKey: ["expense-categories"], queryFn: () => api.get<ExpenseCategory[]>("/expense-categories"), staleTime: 60_000 })
  const [open, setOpen] = useState(false)
  const [category, setCategory] = useState("")
  const [status, setStatus] = useState("")
  const [range, setRange] = useState<DateRange>({ start: "", end: "" })
  const [voiding, setVoiding] = useState<Expense | null>(null)
  const ok = !!range.start && !!range.end
  const { query, data, setPage, search, setSearch, sort, toggleSort } = useTableQuery<Expense>("expenses", "/expenses", {
    filters: { category_id: category || undefined, status: status || undefined, start: ok ? range.start : undefined, end: ok ? range.end : undefined }, defaultSort: "-expense_date",
  })
  const voidIt = useApiMutation((v: { e: Expense; reason: string }) => api.post(`/expenses/${v.e.id}/void`, { reason: v.reason }), { success: "Expense voided", invalidate: [["expenses"], ["dashboard"], ["cash-session"]] })
  const total = data?.items.filter((e) => e.status === "ACTIVE").reduce((s, e) => s + e.amount, 0) ?? 0
  return (
    <>
      <PageHeader title="Expenses" description="Rent, utilities, transport and everything else that isn’t stock."
        actions={<Can perm="expense.create"><Button onClick={() => setOpen(true)}><Plus className="size-4" /> Record expense</Button></Can>} />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search description or number…" />
        <NativeSelect aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} className="w-40"><option value="">All categories</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect>
        <NativeSelect aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-32"><option value="">All</option><option value="ACTIVE">Active</option><option value="VOID">Voided</option></NativeSelect>
        <DateRangeFilter value={range} onChange={setRange} />
      </Toolbar>
      <DataTable<Expense>
        caption="Expenses" page={data} isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} sort={sort} onSort={toggleSort} rowKey={(e) => e.id}
        empty={{ title: "No expenses recorded.", description: "Record rent, electricity, salaries and other costs to see true profit.", action: can("expense.create") ? <Button onClick={() => setOpen(true)}><Plus className="size-4" /> Record expense</Button> : undefined }}
        columns={[
          { id: "no", header: "No.", cell: (e) => <span className="font-mono text-xs">{e.expense_number}</span>, hideOnMobile: true },
          { id: "date", header: "Date", sortKey: "expense_date", cell: (e) => formatDate(e.expense_date) },
          { id: "cat", header: "Category", cell: (e) => <span className="font-medium">{e.category_name}</span> },
          { id: "desc", header: "Description", cell: (e) => <span className="text-muted-foreground">{e.description ?? "—"}</span>, hideOnMobile: true },
          { id: "method", header: "Paid with", cell: (e) => e.payment_method_name, hideOnMobile: true },
          { id: "amount", header: "Amount", sortKey: "amount", align: "right", cell: (e) => <Money value={e.amount} className={e.status === "VOID" ? "text-muted-foreground line-through" : "font-semibold"} /> },
          { id: "status", header: "Status", cell: (e) => <StatusBadge status={e.status} label={e.status === "VOID" ? "Voided" : "Active"} /> },
          { id: "actions", header: <span className="sr-only">Actions</span>, align: "right", cell: (e) => (
            <div className="flex justify-end gap-1">
              {e.has_attachment && <Button variant="ghost" size="icon-sm" aria-label="Download receipt" onClick={() => void downloadFile(`/expenses/${e.id}/attachment`, `${e.expense_number}-receipt`)}><Paperclip className="size-4" /></Button>}
              {e.status === "ACTIVE" && can("expense.delete") && <Button variant="ghost" size="icon-sm" aria-label={`Void ${e.expense_number}`} onClick={() => setVoiding(e)}><Ban className="size-4" /></Button>}
            </div>) },
        ]}
      />
      {data && data.items.length > 0 && <p className="mt-3 text-right text-sm text-muted-foreground">Active expenses on this page: <span className="font-semibold text-foreground tabular">{formatMoney(total)}</span></p>}
      <ExpenseDialog open={open} onClose={() => setOpen(false)} />
      <ConfirmDialog open={!!voiding} onOpenChange={(o) => !o && setVoiding(null)} title={`Void ${voiding?.expense_number}?`} destructive confirmLabel="Void expense"
        description="Expenses are never deleted. The entry stays visible marked as void and cash is returned to your register if it was paid in cash." reason={{ label: "Reason" }} onConfirm={(reason) => voidIt.mutateAsync({ e: voiding!, reason: reason! })} />
    </>
  )
}

/* ------------------------------ cash register ------------------------------ */

function CloseDialog({ session, open, onClose }: { session: CashSession; open: boolean; onClose: () => void }) {
  const [actual, setActual] = useState("")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const diff = actual === "" ? null : Math.round((Number(actual) - session.expected_cash) * 100) / 100
  const close = useApiMutation(
    () => api.post<CashSession>(`/cash-sessions/${session.id}/close`, { actual_cash: Number(actual), reason: reason || undefined }),
    { success: (s) => (s.difference ? `Register closed — difference ${formatMoney(s.difference)}` : "Register closed — cash balanced"), invalidate: [["cash-session"], ["cash-sessions"]], onSuccess: () => { setActual(""); setReason(""); onClose() }, silentError: true },
  )
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (actual === "" || Number(actual) < 0) return setError("Enter the cash you counted in the drawer.")
    if (diff !== 0 && reason.trim().length < 3) return setError("The counted cash differs from the expected cash. Please explain the difference.")
    try { await close.mutateAsync() } catch (err) { setError((err as Error).message) }
  }
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title="Close register" description="Count everything in the drawer, then enter the total." size="sm">
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <dl className="rounded-xl bg-muted/60 p-3"><KeyValue label="Expected cash"><Money value={session.expected_cash} className="text-base font-semibold" /></KeyValue></dl>
        <Field label="Counted cash (৳)" required>{(p) => <Input {...p} type="number" min="0" step="0.01" autoFocus inputMode="decimal" value={actual} onChange={(e) => setActual(e.target.value)} className="h-12 text-lg" />}</Field>
        {diff !== null && (
          <p className={`rounded-lg px-3 py-2 text-sm font-medium ${diff === 0 ? "bg-success/10 text-success" : "bg-warning/15 text-[oklch(0.45_0.12_70)] dark:text-warning"}`} role="status">
            {diff === 0 ? "Perfect — the drawer balances." : `${diff > 0 ? "Over" : "Short"} by ${formatMoney(Math.abs(diff))}`}
          </p>
        )}
        {diff !== null && diff !== 0 && <Field label="Reason for the difference" required>{(p) => <Textarea {...p} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>}
        <SubmitRow onCancel={onClose} submitting={close.isPending} submitLabel="Close register" />
      </form>
    </FormDialog>
  )
}

function MovementDialog({ session, open, onClose }: { session: CashSession; open: boolean; onClose: () => void }) {
  const [direction, setDirection] = useState<"IN" | "OUT">("OUT")
  const [amount, setAmount] = useState("")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const move = useApiMutation(() => api.post(`/cash-sessions/${session.id}/movements`, { direction, amount: Number(amount), reason }), { success: "Cash movement recorded", invalidate: [["cash-session"]], onSuccess: () => { setAmount(""); setReason(""); onClose() }, silentError: true })
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(null)
    if (!(Number(amount) > 0)) return setError("Enter an amount.")
    if (reason.trim().length < 3) return setError("A reason is required.")
    try { await move.mutateAsync() } catch (err) { setError((err as Error).message) }
  }
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title="Cash in / out" description="Record money added to or taken from the drawer (e.g. bank deposit, float top-up)." size="sm">
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <Field label="Direction">{(p) => <NativeSelect {...p} value={direction} onChange={(e) => setDirection(e.target.value as "IN" | "OUT")}><option value="OUT">Take cash out</option><option value="IN">Put cash in</option></NativeSelect>}</Field>
        <Field label="Amount (৳)" required>{(p) => <Input {...p} type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />}</Field>
        <Field label="Reason" required>{(p) => <Input {...p} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        <SubmitRow onCancel={onClose} submitting={move.isPending} />
      </form>
    </FormDialog>
  )
}

const BREAKDOWN_LABEL: Record<string, string> = { OPENING: "Opening cash", SALE: "Cash sales", REFUND: "Refunds paid", EXPENSE: "Cash expenses", CASH_IN: "Cash in", CASH_OUT: "Cash out", CUSTOMER_PAYMENT: "Customer payments", SUPPLIER_PAYMENT: "Supplier payments", SALE_VOID: "Voided sales" }

export function CashRegisterPage() {
  const { can } = useAuth()
  const current = useCurrentSession()
  const [closing, setClosing] = useState(false)
  const [moving, setMoving] = useState(false)
  const [range, setRange] = useState<DateRange>({ start: "", end: "" })
  const ok = !!range.start && !!range.end
  const { query, data, setPage } = useTableQuery<CashSession>("cash-sessions", "/cash-sessions", { filters: { start: ok ? range.start : undefined, end: ok ? range.end : undefined } })
  const s = current.data
  return (
    <>
      <PageHeader title="Cash register" description="Open the drawer, track cash in and out, and reconcile at close." />
      {current.isLoading ? <PageLoading /> : s ? (
        <SectionCard className="mb-6" title={<span className="flex items-center gap-2"><Landmark className="size-4" /> {s.register_name} · open since {formatDateTime(s.opened_at)}</span>}
          actions={<div className="flex gap-2"><Can perm="register.use"><Button variant="outline" size="sm" onClick={() => setMoving(true)}>Cash in / out</Button><Button size="sm" onClick={() => setClosing(true)}>Close register</Button></Can></div>}>
          <div className="grid gap-4 md:grid-cols-[260px_1fr]">
            <div className="rounded-xl bg-primary/8 p-4"><p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Expected in drawer</p><p className="mt-1 text-3xl font-bold tabular">{formatMoney(s.expected_cash)}</p></div>
            <dl className="grid gap-x-8 sm:grid-cols-2">
              {Object.entries(s.breakdown).map(([k, v]) => <KeyValue key={k} label={BREAKDOWN_LABEL[k] ?? humanize(k)}><Money value={v} signed={v < 0} /></KeyValue>)}
            </dl>
          </div>
        </SectionCard>
      ) : can("register.use") ? (
        <div className="mb-6"><OpenRegisterCard /></div>
      ) : null}

      <h2 className="mb-2 text-sm font-semibold">Session history</h2>
      <Toolbar><DateRangeFilter value={range} onChange={setRange} /></Toolbar>
      <DataTable<CashSession>
        page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(x) => x.id}
        empty={{ title: "No register sessions yet.", description: "Sessions appear here after a register is opened." }}
        columns={[
          { id: "reg", header: "Register", cell: (x) => <div><div className="font-medium">{x.register_name}</div><div className="text-xs text-muted-foreground">{x.opened_by_name}</div></div> },
          { id: "opened", header: "Opened", cell: (x) => <span className="whitespace-nowrap">{formatDateTime(x.opened_at)}</span> },
          { id: "closed", header: "Closed", cell: (x) => (x.closed_at ? <span className="whitespace-nowrap">{formatDateTime(x.closed_at)}</span> : "—"), hideOnMobile: true },
          { id: "open", header: "Opening", align: "right", cell: (x) => <Money value={x.opening_cash} className="text-muted-foreground" />, hideOnMobile: true },
          { id: "exp", header: "Expected", align: "right", cell: (x) => <Money value={x.expected_cash} /> },
          { id: "act", header: "Counted", align: "right", cell: (x) => (x.actual_cash === null ? "—" : <Money value={x.actual_cash} />), hideOnMobile: true },
          { id: "diff", header: "Difference", align: "right", cell: (x) => (x.difference === null ? "—" : <Money value={x.difference} signed />) },
          { id: "reason", header: "Reason", cell: (x) => <span className="text-muted-foreground">{x.discrepancy_reason ?? ""}</span>, hideOnMobile: true },
          { id: "st", header: "Status", cell: (x) => <StatusBadge status={x.status} /> },
        ]}
      />
      {s && <CloseDialog session={s} open={closing} onClose={() => setClosing(false)} />}
      {s && <MovementDialog session={s} open={moving} onClose={() => setMoving(false)} />}
    </>
  )
}
