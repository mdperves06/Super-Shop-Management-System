"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQuery } from "@tanstack/react-query"
import { FileText, HandCoins, Pencil, Plus } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
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
import { formatDate, formatDateTime, formatMoney } from "@/lib/format"
import { searchCustomers } from "@/services/lookups"
import type { Customer, CustomerProfile, Sale } from "@/types/api"

const PHONE = /^[+0-9][0-9\-\s()]{5,24}$/
const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(150),
  phone: z.string().trim().optional().refine((v) => !v || PHONE.test(v), "Enter a valid phone number (e.g. 01712345678)"),
  email: z.string().trim().optional().refine((v) => !v || /^\S+@\S+\.\S+$/.test(v), "Enter a valid email"),
  address: z.string().optional(),
  customer_type: z.enum(["RETAIL", "WHOLESALE", "VIP"]),
  discount_percent: z.number().min(0).max(100),
  credit_limit: z.number().min(0, "Cannot be negative"),
  opening_balance: z.number().min(0, "Cannot be negative").optional(),
  is_active: z.boolean(),
})
type Values = z.infer<typeof schema>

export function CustomerDialog({ customer, onClose, onSaved }: { customer: Customer | "new" | null; onClose: () => void; onSaved?: (c: Customer) => void }) {
  const editing = customer && customer !== "new" ? customer : null
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    values: editing
      ? { name: editing.name, phone: editing.phone ?? "", email: editing.email ?? "", address: editing.address ?? "", customer_type: editing.customer_type as Values["customer_type"], discount_percent: editing.discount_percent, credit_limit: editing.credit_limit, is_active: editing.is_active }
      : { name: "", phone: "", email: "", address: "", customer_type: "RETAIL", discount_percent: 0, credit_limit: 0, opening_balance: 0, is_active: true },
  })
  const [serverError, setServerError] = useState<string | null>(null)
  const save = useApiMutation(
    (v: Values) => {
      const body: Record<string, unknown> = {}
      for (const [k, val] of Object.entries(v)) body[k] = val === "" ? null : val
      if (editing) { delete body.opening_balance; return api.patch<Customer>(`/customers/${editing.id}`, body) }
      return api.post<Customer>("/customers", body)
    },
    { success: "Customer saved", invalidate: [["customers"]], onSuccess: (c) => { onSaved?.(c); onClose() }, silentError: true },
  )
  return (
    <FormDialog open={!!customer} onOpenChange={(o) => !o && onClose()} title={editing ? "Edit customer" : "New customer"} size="lg">
      <form onSubmit={handleSubmit(async (v) => { setServerError(null); try { await save.mutateAsync(v) } catch (e) { setServerError((e as Error).message) } })} className="space-y-4" noValidate>
        {serverError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{serverError}</div>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" required error={errors.name?.message}>{(p) => <Input {...p} autoFocus {...register("name")} />}</Field>
          <Field label="Phone" error={errors.phone?.message}>{(p) => <Input {...p} type="tel" placeholder="01XXXXXXXXX" {...register("phone")} />}</Field>
          <Field label="Email" error={errors.email?.message}>{(p) => <Input {...p} type="email" {...register("email")} />}</Field>
          <Field label="Customer type">{(p) => <NativeSelect {...p} {...register("customer_type")}><option value="RETAIL">Retail</option><option value="WHOLESALE">Wholesale</option><option value="VIP">VIP</option></NativeSelect>}</Field>
          <Field label="Credit limit (৳)" error={errors.credit_limit?.message} hint="0 = no credit allowed">{(p) => <Input {...p} type="number" min="0" step="0.01" {...register("credit_limit", { valueAsNumber: true })} />}</Field>
          <Field label="Standing discount %" error={errors.discount_percent?.message} hint="Applied to every purchase">{(p) => <Input {...p} type="number" min="0" max="100" step="0.01" {...register("discount_percent", { valueAsNumber: true })} />}</Field>
          {!editing && <Field label="Opening balance (they owe)" error={errors.opening_balance?.message}>{(p) => <Input {...p} type="number" min="0" step="0.01" {...register("opening_balance", { valueAsNumber: true })} />}</Field>}
          <Field label="Address" className="sm:col-span-2">{(p) => <Textarea {...p} rows={2} {...register("address")} />}</Field>
        </div>
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={watch("is_active")} onCheckedChange={(c) => setValue("is_active", !!c)} /> Active</label>
        <SubmitRow onCancel={onClose} submitting={save.isPending} />
      </form>
    </FormDialog>
  )
}

export function CustomersList() {
  const router = useRouter()
  const { can } = useAuth()
  const [dialog, setDialog] = useState<Customer | "new" | null>(null)
  const [owing, setOwing] = useState("")
  const [type, setType] = useState("")
  const { query, data, setPage, search, setSearch, sort, toggleSort } = useTableQuery<Customer>("customers", "/customers", { filters: { has_balance: owing || undefined, customer_type: type || undefined }, defaultSort: "name" })
  return (
    <>
      <PageHeader title="Customers" description="Regulars, wholesale accounts and credit balances."
        actions={<Can perm="customer.create"><Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add customer</Button></Can>} />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search name, phone or code…" />
        <NativeSelect aria-label="Type" value={type} onChange={(e) => setType(e.target.value)} className="w-36"><option value="">All types</option><option value="RETAIL">Retail</option><option value="WHOLESALE">Wholesale</option><option value="VIP">VIP</option></NativeSelect>
        <NativeSelect aria-label="Balance filter" value={owing} onChange={(e) => setOwing(e.target.value)} className="w-44"><option value="">All customers</option><option value="true">Owe us money</option></NativeSelect>
      </Toolbar>
      <DataTable<Customer>
        caption="Customers" page={data} isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} sort={sort} onSort={toggleSort}
        rowKey={(c) => c.id} onRowClick={(c) => router.push(`/customers/${c.id}`)}
        empty={{ title: "No customers found.", description: "Add customers to track their purchases, loyalty points and credit.", action: can("customer.create") ? <Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add customer</Button> : undefined }}
        columns={[
          { id: "name", header: "Customer", sortKey: "name", cell: (c) => <div><div className="font-medium">{c.name}</div><div className="font-mono text-xs text-muted-foreground">{c.code}</div></div> },
          { id: "phone", header: "Phone", cell: (c) => c.phone ?? "—" },
          { id: "type", header: "Type", cell: (c) => <StatusBadge status={c.customer_type} tone={c.customer_type === "VIP" ? "info" : "neutral"} label={c.customer_type[0] + c.customer_type.slice(1).toLowerCase()} />, hideOnMobile: true },
          { id: "points", header: "Points", sortKey: "loyalty_points", align: "right", cell: (c) => c.loyalty_points, hideOnMobile: true },
          { id: "limit", header: "Credit limit", align: "right", cell: (c) => <Money value={c.credit_limit} className="text-muted-foreground" />, hideOnMobile: true },
          { id: "balance", header: "Owes us", sortKey: "balance", align: "right", cell: (c) => <Money value={c.balance} className={c.balance > 0 ? "font-semibold text-destructive" : "text-muted-foreground"} /> },
        ]}
      />
      <CustomerDialog customer={dialog} onClose={() => setDialog(null)} />
    </>
  )
}

export function CustomerProfilePage({ id }: { id: number }) {
  const { can } = useAuth()
  const { data: c, isLoading, error } = useQuery({ queryKey: ["customers", "profile", id], queryFn: () => api.get<CustomerProfile>(`/customers/${id}`) })
  const [edit, setEdit] = useState(false)
  const [pay, setPay] = useState(false)
  const [adjust, setAdjust] = useState(false)
  if (isLoading) return <PageLoading />
  if (error || !c) return <p className="mt-10 text-center text-sm text-muted-foreground" role="alert">{errorMessage(error ?? new Error("Customer not found"))}</p>
  return (
    <>
      <PageHeader back={{ href: "/customers", label: "Customers" }} title={c.name}
        description={<span className="flex flex-wrap items-center gap-x-3 gap-y-1"><span className="font-mono text-xs">{c.code}</span>{c.phone && <span>{c.phone}</span>}<StatusBadge status={c.customer_type} tone="info" label={c.customer_type[0] + c.customer_type.slice(1).toLowerCase()} /></span>}
        actions={<>
          <Button variant="outline" onClick={() => void openFile(`/documents/customers/${id}/statement.pdf`)}><FileText className="size-4" /> Statement</Button>
          <Can perm="customer.update"><Button variant="outline" onClick={() => setEdit(true)}><Pencil className="size-4" /> Edit</Button></Can>
          <Can perm="customer.payment"><Button onClick={() => setPay(true)} disabled={c.balance <= 0}><HandCoins className="size-4" /> Receive payment</Button></Can>
        </>} />
      <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-5">
        <StatCard label="Balance due" value={<Money value={c.balance} />} tone={c.balance > 0 ? "danger" : "neutral"} hint={c.credit_limit ? `Limit ${formatMoney(c.credit_limit)}` : "No credit"} />
        <StatCard label="Purchases" value={<Money value={c.total_purchases} />} hint={`${c.sale_count} sales`} />
        <StatCard label="Payments received" value={<Money value={c.total_paid} />} />
        <StatCard label="Returns" value={<Money value={c.total_returns} />} />
        <StatCard label="Loyalty points" value={c.loyalty_points} hint={c.last_purchase_at ? `Last visit ${formatDate(c.last_purchase_at)}` : "No visits yet"} />
      </div>
      <Tabs defaultValue="ledger">
        <TabsList className="mb-4"><TabsTrigger value="ledger">Ledger</TabsTrigger><TabsTrigger value="sales">Sales</TabsTrigger><TabsTrigger value="details">Details</TabsTrigger></TabsList>
        <TabsContent value="ledger"><LedgerTable basePath="/customers" id={id} owed="They owe" /></TabsContent>
        <TabsContent value="sales"><CustomerSales id={id} /></TabsContent>
        <TabsContent value="details">
          <SectionCard title="Customer details" actions={can("customer.update") ? <Button variant="outline" size="sm" onClick={() => setAdjust(true)}>Adjust balance</Button> : undefined}>
            <dl className="grid gap-x-8 md:grid-cols-2">
              <KeyValue label="Email">{c.email ?? "—"}</KeyValue><KeyValue label="Standing discount">{c.discount_percent}%</KeyValue>
              <KeyValue label="Opening balance"><Money value={c.opening_balance} /></KeyValue><KeyValue label="Customer since">{formatDate(c.created_at)}</KeyValue>
              <KeyValue label="Address">{c.address ?? "—"}</KeyValue>
            </dl>
          </SectionCard>
        </TabsContent>
      </Tabs>
      <CustomerDialog customer={edit ? c : null} onClose={() => setEdit(false)} />
      <PaymentDialog open={pay} onClose={() => setPay(false)} basePath="/customers" id={id} name={c.name} balance={c.balance} />
      <AdjustBalanceDialog open={adjust} onClose={() => setAdjust(false)} basePath="/customers" id={id} name={c.name} balance={c.balance} />
    </>
  )
}

function CustomerSales({ id }: { id: number }) {
  const router = useRouter()
  const { can } = useAuth()
  const { query, data, setPage } = useTableQuery<Sale>(`customer-sales-${id}`, "/sales", { filters: { customer_id: id }, enabled: can("sale.read") })
  if (!can("sale.read")) return <p className="text-sm text-muted-foreground">You don’t have access to sales.</p>
  return (
    <DataTable<Sale> page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(s) => s.id} onRowClick={(s) => router.push(`/sales/${s.id}`)}
      empty={{ title: "No purchases yet." }}
      columns={[
        { id: "inv", header: "Invoice", cell: (s) => <span className="font-mono text-xs font-medium">{s.invoice_number}</span> },
        { id: "date", header: "Date", cell: (s) => formatDateTime(s.sale_date) },
        { id: "total", header: "Total", align: "right", cell: (s) => <Money value={s.total_amount} /> },
        { id: "due", header: "Due", align: "right", cell: (s) => <Money value={s.due_amount} className={s.due_amount > 0 ? "text-destructive" : "text-muted-foreground"} /> },
        { id: "status", header: "Status", cell: (s) => <StatusBadge status={s.status} /> },
      ]} />
  )
}

export function CustomerLedgerPage() {
  const [customer, setCustomer] = useState<Option | null>(null)
  return (
    <>
      <PageHeader title="Customer ledger" description="Purchases, payments and returns for one customer, with a running balance." />
      <div className="mb-4 max-w-sm"><AsyncCombobox value={customer} onChange={setCustomer} fetcher={searchCustomers} queryKey="customers" placeholder="Choose a customer…" /></div>
      {customer ? (
        <>
          <div className="mb-3 flex gap-2"><Button variant="outline" size="sm" render={<Link href={`/customers/${customer.id}`} />}>Open profile</Button><Button variant="outline" size="sm" onClick={() => void openFile(`/documents/customers/${customer.id}/statement.pdf`)}><FileText className="size-4" /> Statement PDF</Button></div>
          <LedgerTable basePath="/customers" id={customer.id} owed="They owe" />
        </>
      ) : <div className="rounded-xl border border-dashed bg-card py-16 text-center text-sm text-muted-foreground">Choose a customer to see the ledger.</div>}
    </>
  )
}
