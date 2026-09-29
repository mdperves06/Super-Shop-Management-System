"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQuery } from "@tanstack/react-query"
import { FileText, HandCoins, Pencil, Plus } from "lucide-react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { AsyncCombobox, type Option } from "@/components/shared/combobox"
import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { FormDialog, SubmitRow } from "@/components/shared/dialogs"
import { Can, Field, KeyValue, Money, NativeSelect, PageHeader, PageLoading, SectionCard, StatCard, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { AdjustBalanceDialog, LedgerTable, PaymentDialog } from "@/features/parties/party-shared"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api, errorMessage, openFile } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDate } from "@/lib/format"
import { searchSuppliers } from "@/services/lookups"
import type { Purchase, Supplier, SupplierProfile } from "@/types/api"

const PHONE = /^[+0-9][0-9\-\s()]{5,24}$/
const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(150),
  company: z.string().trim().max(150).optional(),
  phone: z.string().trim().optional().refine((v) => !v || PHONE.test(v), "Enter a valid phone number"),
  email: z.string().trim().optional().refine((v) => !v || /^\S+@\S+\.\S+$/.test(v), "Enter a valid email"),
  address: z.string().optional(),
  contact_person: z.string().trim().max(150).optional(),
  tax_id: z.string().trim().max(50).optional(),
  payment_terms_days: z.number().int().min(0).max(365),
  opening_balance: z.number().min(0, "Cannot be negative").optional(),
  notes: z.string().optional(),
  is_active: z.boolean(),
})
type Values = z.infer<typeof schema>

function SupplierDialog({ supplier, onClose }: { supplier: Supplier | "new" | null; onClose: () => void }) {
  const editing = supplier && supplier !== "new" ? supplier : null
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    values: editing
      ? { name: editing.name, company: editing.company ?? "", phone: editing.phone ?? "", email: editing.email ?? "", address: editing.address ?? "", contact_person: editing.contact_person ?? "", tax_id: editing.tax_id ?? "", payment_terms_days: editing.payment_terms_days, notes: editing.notes ?? "", is_active: editing.is_active }
      : { name: "", company: "", phone: "", email: "", address: "", contact_person: "", tax_id: "", payment_terms_days: 0, opening_balance: 0, notes: "", is_active: true },
  })
  const [serverError, setServerError] = useState<string | null>(null)
  const save = useApiMutation(
    (v: Values) => {
      const body: Record<string, unknown> = {}
      for (const [k, val] of Object.entries(v)) body[k] = val === "" ? null : val
      if (editing) { delete body.opening_balance; return api.patch(`/suppliers/${editing.id}`, body) }
      return api.post("/suppliers", body)
    },
    { success: "Supplier saved", invalidate: [["suppliers"]], onSuccess: onClose, silentError: true },
  )
  return (
    <FormDialog open={!!supplier} onOpenChange={(o) => !o && onClose()} title={editing ? "Edit supplier" : "New supplier"} size="lg">
      <form onSubmit={handleSubmit(async (v) => { setServerError(null); try { await save.mutateAsync(v) } catch (e) { setServerError((e as Error).message) } })} className="space-y-4" noValidate>
        {serverError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{serverError}</div>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Supplier name" required error={errors.name?.message}>{(p) => <Input {...p} autoFocus {...register("name")} />}</Field>
          <Field label="Company">{(p) => <Input {...p} {...register("company")} />}</Field>
          <Field label="Phone" error={errors.phone?.message}>{(p) => <Input {...p} type="tel" placeholder="01XXXXXXXXX" {...register("phone")} />}</Field>
          <Field label="Email" error={errors.email?.message}>{(p) => <Input {...p} type="email" {...register("email")} />}</Field>
          <Field label="Contact person">{(p) => <Input {...p} {...register("contact_person")} />}</Field>
          <Field label="BIN / TIN" hint="Tax or VAT registration number">{(p) => <Input {...p} {...register("tax_id")} />}</Field>
          <Field label="Payment terms (days)" error={errors.payment_terms_days?.message}>{(p) => <Input {...p} type="number" min="0" {...register("payment_terms_days", { valueAsNumber: true })} />}</Field>
          {!editing && <Field label="Opening balance (we owe)" error={errors.opening_balance?.message} hint="Amount already owed before using this system">{(p) => <Input {...p} type="number" min="0" step="0.01" {...register("opening_balance", { valueAsNumber: true })} />}</Field>}
          <Field label="Address" className="sm:col-span-2">{(p) => <Textarea {...p} rows={2} {...register("address")} />}</Field>
          <Field label="Notes" className="sm:col-span-2">{(p) => <Textarea {...p} rows={2} {...register("notes")} />}</Field>
        </div>
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={watch("is_active")} onCheckedChange={(c) => setValue("is_active", !!c)} /> Active</label>
        <SubmitRow onCancel={onClose} submitting={save.isPending} />
      </form>
    </FormDialog>
  )
}

export function SuppliersList() {
  const router = useRouter()
  const { can } = useAuth()
  const [dialog, setDialog] = useState<Supplier | "new" | null>(null)
  const [owing, setOwing] = useState("")
  const { query, data, setPage, search, setSearch, sort, toggleSort } = useTableQuery<Supplier>("suppliers", "/suppliers", { filters: { has_balance: owing || undefined }, defaultSort: "name" })
  return (
    <>
      <PageHeader title="Suppliers" description="Who you buy from and what you owe them."
        actions={<Can perm="supplier.create"><Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add supplier</Button></Can>} />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search name, company or phone…" />
        <NativeSelect aria-label="Balance filter" value={owing} onChange={(e) => setOwing(e.target.value)} className="w-44"><option value="">All suppliers</option><option value="true">We owe money</option></NativeSelect>
      </Toolbar>
      <DataTable<Supplier>
        caption="Suppliers" page={data} isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} sort={sort} onSort={toggleSort}
        rowKey={(s) => s.id} onRowClick={(s) => router.push(`/suppliers/${s.id}`)}
        empty={{ title: "No suppliers found.", description: "Add your suppliers to start creating purchase orders.", action: can("supplier.create") ? <Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add supplier</Button> : undefined }}
        columns={[
          { id: "name", header: "Supplier", sortKey: "name", cell: (s) => <div><div className="font-medium">{s.name}</div>{s.company && <div className="text-xs text-muted-foreground">{s.company}</div>}</div> },
          { id: "code", header: "Code", sortKey: "code", cell: (s) => <span className="font-mono text-xs">{s.code}</span>, hideOnMobile: true },
          { id: "phone", header: "Phone", cell: (s) => s.phone ?? "—", hideOnMobile: true },
          { id: "terms", header: "Terms", align: "right", cell: (s) => (s.payment_terms_days ? `${s.payment_terms_days} days` : "Cash"), hideOnMobile: true },
          { id: "balance", header: "We owe", sortKey: "balance", align: "right", cell: (s) => <Money value={s.balance} className={s.balance > 0 ? "font-semibold" : "text-muted-foreground"} /> },
          { id: "status", header: "Status", cell: (s) => <StatusBadge status={s.is_active ? "ACTIVE" : "INACTIVE"} />, hideOnMobile: true },
        ]}
      />
      <SupplierDialog supplier={dialog} onClose={() => setDialog(null)} />
    </>
  )
}

function SupplierProfileInner({ id }: { id: number }) {
  const { can } = useAuth()
  const params = useSearchParams()
  const { data: s, isLoading, error } = useQuery({ queryKey: ["suppliers", "profile", id], queryFn: () => api.get<SupplierProfile>(`/suppliers/${id}`) })
  const [edit, setEdit] = useState(false)
  const [pay, setPay] = useState(false)
  const [adjust, setAdjust] = useState(false)
  useEffect(() => { if (params.get("pay") === "1") setPay(true) }, [params]) // eslint-disable-line react-hooks/set-state-in-effect
  if (isLoading) return <PageLoading />
  if (error || !s) return <p className="mt-10 text-center text-sm text-muted-foreground" role="alert">{errorMessage(error ?? new Error("Supplier not found"))}</p>
  const purchaseId = params.get("po") ? Number(params.get("po")) : undefined
  return (
    <>
      <PageHeader back={{ href: "/suppliers", label: "Suppliers" }} title={s.name}
        description={<span className="flex flex-wrap items-center gap-x-3 gap-y-1"><span className="font-mono text-xs">{s.code}</span>{s.company && <span>{s.company}</span>}{s.phone && <span>{s.phone}</span>}<StatusBadge status={s.is_active ? "ACTIVE" : "INACTIVE"} /></span>}
        actions={<>
          <Button variant="outline" onClick={() => void openFile(`/documents/suppliers/${id}/statement.pdf`)}><FileText className="size-4" /> Statement</Button>
          <Can perm="supplier.update"><Button variant="outline" onClick={() => setEdit(true)}><Pencil className="size-4" /> Edit</Button></Can>
          <Can perm="supplier.payment"><Button onClick={() => setPay(true)} disabled={s.balance <= 0}><HandCoins className="size-4" /> Record payment</Button></Can>
        </>} />
      <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard label="Outstanding balance" value={<Money value={s.balance} />} tone={s.balance > 0 ? "warning" : "neutral"} />
        <StatCard label="Total purchases" value={<Money value={s.total_purchases} />} hint={`${s.purchase_count} orders`} />
        <StatCard label="Total paid" value={<Money value={s.total_paid} />} />
        <StatCard label="Returns" value={<Money value={s.total_returns} />} />
      </div>
      <Tabs defaultValue="ledger">
        <TabsList className="mb-4"><TabsTrigger value="ledger">Ledger</TabsTrigger><TabsTrigger value="purchases">Purchases</TabsTrigger><TabsTrigger value="details">Details</TabsTrigger></TabsList>
        <TabsContent value="ledger"><LedgerTable basePath="/suppliers" id={id} owed="We owe" /></TabsContent>
        <TabsContent value="purchases"><SupplierPurchases id={id} /></TabsContent>
        <TabsContent value="details">
          <SectionCard title="Supplier details" actions={can("supplier.update") ? <Button variant="outline" size="sm" onClick={() => setAdjust(true)}>Adjust balance</Button> : undefined}>
            <dl className="grid gap-x-8 md:grid-cols-2">
              <KeyValue label="Contact person">{s.contact_person ?? "—"}</KeyValue><KeyValue label="Email">{s.email ?? "—"}</KeyValue>
              <KeyValue label="BIN / TIN">{s.tax_id ?? "—"}</KeyValue><KeyValue label="Payment terms">{s.payment_terms_days ? `${s.payment_terms_days} days` : "Cash on delivery"}</KeyValue>
              <KeyValue label="Opening balance"><Money value={s.opening_balance} /></KeyValue><KeyValue label="Since">{formatDate(s.created_at)}</KeyValue>
              <KeyValue label="Address">{s.address ?? "—"}</KeyValue><KeyValue label="Notes">{s.notes ?? "—"}</KeyValue>
            </dl>
          </SectionCard>
        </TabsContent>
      </Tabs>
      <SupplierDialog supplier={edit ? s : null} onClose={() => setEdit(false)} />
      <PaymentDialog open={pay} onClose={() => setPay(false)} basePath="/suppliers" id={id} name={s.name} balance={s.balance} purchaseId={purchaseId} />
      <AdjustBalanceDialog open={adjust} onClose={() => setAdjust(false)} basePath="/suppliers" id={id} name={s.name} balance={s.balance} />
    </>
  )
}

function SupplierPurchases({ id }: { id: number }) {
  const router = useRouter()
  const { query, data, setPage } = useTableQuery<Purchase>(`supplier-purchases-${id}`, "/purchases", { filters: { supplier_id: id }, defaultSort: "-order_date" })
  return (
    <DataTable<Purchase> page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(p) => p.id} onRowClick={(p) => router.push(`/purchases/${p.id}`)}
      empty={{ title: "No purchase orders for this supplier." }}
      columns={[
        { id: "po", header: "PO", cell: (p) => <span className="font-mono text-xs font-medium">{p.po_number}</span> },
        { id: "date", header: "Date", cell: (p) => formatDate(p.order_date) },
        { id: "total", header: "Total", align: "right", cell: (p) => <Money value={p.total_amount} /> },
        { id: "paid", header: "Paid", align: "right", cell: (p) => <Money value={p.paid_amount} className="text-muted-foreground" />, hideOnMobile: true },
        { id: "status", header: "Status", cell: (p) => <StatusBadge status={p.status} /> },
      ]} />
  )
}

export function SupplierProfilePage({ id }: { id: number }) {
  return <Suspense fallback={<PageLoading />}><SupplierProfileInner id={id} /></Suspense>
}

/** "Supplier Ledger" menu entry: choose a supplier, see the full ledger. */
export function SupplierLedgerPage() {
  const [supplier, setSupplier] = useState<Option | null>(null)
  return (
    <>
      <PageHeader title="Supplier ledger" description="Purchases, payments and returns for one supplier, with a running balance." />
      <div className="mb-4 max-w-sm"><AsyncCombobox value={supplier} onChange={setSupplier} fetcher={searchSuppliers} queryKey="suppliers" placeholder="Choose a supplier…" /></div>
      {supplier ? (
        <>
          <div className="mb-3 flex gap-2"><Button variant="outline" size="sm" render={<Link href={`/suppliers/${supplier.id}`} />}>Open profile</Button><Button variant="outline" size="sm" onClick={() => void openFile(`/documents/suppliers/${supplier.id}/statement.pdf`)}><FileText className="size-4" /> Statement PDF</Button></div>
          <LedgerTable basePath="/suppliers" id={supplier.id} owed="We owe" />
        </>
      ) : <div className="rounded-xl border border-dashed bg-card py-16 text-center text-sm text-muted-foreground">Choose a supplier to see the ledger.</div>}
    </>
  )
}
