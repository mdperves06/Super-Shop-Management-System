"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQuery } from "@tanstack/react-query"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { AsyncCombobox, type Option } from "@/components/shared/combobox"
import { DataTable } from "@/components/shared/data-table"
import { ConfirmDialog, FormDialog, SubmitRow } from "@/components/shared/dialogs"
import { Field, Money, NativeSelect, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDate, formatDateTime, formatNumber } from "@/lib/format"
import { searchProducts, useCategories, usePaymentMethods, useTaxRates, useUnits } from "@/services/lookups"
import type { Discount, PaymentMethod, Promotion, TaxRate, Unit } from "@/types/api"

function Toolbar2({ title, description, onAdd, addLabel }: { title: string; description: string; onAdd?: () => void; addLabel: string }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-3">
      <div><h2 className="text-base font-semibold">{title}</h2><p className="text-sm text-muted-foreground">{description}</p></div>
      {onAdd && <Button onClick={onAdd}><Plus className="size-4" /> {addLabel}</Button>}
    </div>
  )
}
const listPage = <T,>(items: T[] = []) => ({ items, total: items.length, page: 1, page_size: items.length || 1, pages: 1 })
const ErrorBox = ({ msg }: { msg: string | null }) => (msg ? <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{msg}</div> : null)

/* ---------------------------------- tax ---------------------------------- */

const taxSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(80),
  rate: z.number({ error: "Enter a rate" }).min(0).max(100, "Cannot exceed 100%"),
  effective_from: z.string().optional(),
  effective_to: z.string().optional(),
  is_active: z.boolean(),
  is_default: z.boolean(),
})
type TaxValues = z.infer<typeof taxSchema>

export function TaxSettings() {
  const { can } = useAuth()
  const { data, isLoading, error, refetch } = useTaxRates()
  const [dialog, setDialog] = useState<TaxRate | "new" | null>(null)
  const editing = dialog && dialog !== "new" ? dialog : null
  const [serverError, setServerError] = useState<string | null>(null)
  const { register, handleSubmit, formState: { errors } } = useForm<TaxValues>({
    resolver: zodResolver(taxSchema),
    values: editing ? { name: editing.name, rate: editing.rate, effective_from: editing.effective_from ?? "", effective_to: editing.effective_to ?? "", is_active: editing.is_active, is_default: editing.is_default } : { name: "", rate: 15, effective_from: "", effective_to: "", is_active: true, is_default: false },
  })
  const save = useApiMutation((v: TaxValues) => { const b = { ...v, effective_from: v.effective_from || null, effective_to: v.effective_to || null }; return editing ? api.put(`/tax-rates/${editing.id}`, b) : api.post("/tax-rates", b) }, { success: "Tax rate saved", invalidate: [["tax-rates"]], onSuccess: () => setDialog(null), silentError: true })
  const editable = can("settings.update")
  return (
    <>
      <Toolbar2 title="Tax / VAT rates" description="Rates are never hard-coded. Add a new rate with an effective date when the law changes." onAdd={editable ? () => setDialog("new") : undefined} addLabel="Add tax rate" />
      <DataTable<TaxRate> page={listPage(data)} isLoading={isLoading} error={error} onRetry={() => refetch()} rowKey={(t) => t.id}
        empty={{ title: "No tax rates configured." }}
        columns={[
          { id: "name", header: "Name", cell: (t) => <span className="font-medium">{t.name}</span> },
          { id: "rate", header: "Rate", align: "right", cell: (t) => `${t.rate}%` },
          { id: "from", header: "Effective from", cell: (t) => formatDate(t.effective_from), hideOnMobile: true },
          { id: "to", header: "Until", cell: (t) => (t.effective_to ? formatDate(t.effective_to) : "open-ended"), hideOnMobile: true },
          { id: "st", header: "Status", cell: (t) => <span className="flex gap-1"><StatusBadge status={t.is_active ? "ACTIVE" : "INACTIVE"} />{t.is_default && <StatusBadge status="ACTIVE" tone="info" label="Default" />}</span> },
          { id: "a", header: <span className="sr-only">Actions</span>, align: "right", cell: (t) => editable ? <Button variant="ghost" size="icon-sm" aria-label={`Edit ${t.name}`} onClick={() => setDialog(t)}><Pencil className="size-4" /></Button> : null },
        ]} />
      <FormDialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)} title={editing ? "Edit tax rate" : "New tax rate"} size="sm">
        <form onSubmit={handleSubmit(async (v) => { setServerError(null); try { await save.mutateAsync(v) } catch (e) { setServerError((e as Error).message) } })} className="space-y-4" noValidate>
          <ErrorBox msg={serverError} />
          <Field label="Name" required error={errors.name?.message}>{(p) => <Input {...p} autoFocus {...register("name")} />}</Field>
          <Field label="Rate (%)" required error={errors.rate?.message}>{(p) => <Input {...p} type="number" step="0.01" min="0" max="100" {...register("rate", { valueAsNumber: true })} />}</Field>
          <div className="grid grid-cols-2 gap-3"><Field label="Effective from">{(p) => <Input {...p} type="date" {...register("effective_from")} />}</Field><Field label="Effective until">{(p) => <Input {...p} type="date" {...register("effective_to")} />}</Field></div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" {...register("is_active")} /> Active</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" {...register("is_default")} /> Default rate for new products</label>
          <SubmitRow onCancel={() => setDialog(null)} submitting={save.isPending} />
        </form>
      </FormDialog>
    </>
  )
}

/* ----------------------------- payment methods ----------------------------- */

const pmSchema = z.object({ code: z.string().trim().min(1, "Code is required").max(30), name: z.string().trim().min(1, "Name is required").max(80), method_type: z.enum(["CASH", "CARD", "MOBILE", "BANK", "OTHER"]), requires_reference: z.boolean(), is_active: z.boolean(), sort_order: z.number().int() })
type PmValues = z.infer<typeof pmSchema>

export function PaymentMethodSettings() {
  const { can } = useAuth()
  const { data, isLoading, error, refetch } = usePaymentMethods(true)
  const [dialog, setDialog] = useState<PaymentMethod | "new" | null>(null)
  const editing = dialog && dialog !== "new" ? dialog : null
  const [serverError, setServerError] = useState<string | null>(null)
  const { register, handleSubmit, formState: { errors } } = useForm<PmValues>({
    resolver: zodResolver(pmSchema),
    values: editing ? { code: editing.code, name: editing.name, method_type: editing.method_type as PmValues["method_type"], requires_reference: editing.requires_reference, is_active: editing.is_active, sort_order: editing.sort_order } : { code: "", name: "", method_type: "MOBILE", requires_reference: true, is_active: true, sort_order: 10 },
  })
  const save = useApiMutation((v: PmValues) => (editing ? api.put(`/payment-methods/${editing.id}`, v) : api.post("/payment-methods", v)), { success: "Payment method saved", invalidate: [["payment-methods"]], onSuccess: () => setDialog(null), silentError: true })
  const editable = can("settings.update")
  return (
    <>
      <Toolbar2 title="Payment methods" description="Enable the ways customers can pay. Mobile banking (bKash, Nagad, Rocket) records a transaction ID — no external gateway is called." onAdd={editable ? () => setDialog("new") : undefined} addLabel="Add method" />
      <DataTable<PaymentMethod> page={listPage(data)} isLoading={isLoading} error={error} onRetry={() => refetch()} rowKey={(m) => m.id} empty={{ title: "No payment methods." }}
        columns={[
          { id: "name", header: "Name", cell: (m) => <span className="font-medium">{m.name}</span> },
          { id: "code", header: "Code", cell: (m) => <span className="font-mono text-xs">{m.code}</span>, hideOnMobile: true },
          { id: "type", header: "Type", cell: (m) => m.method_type[0] + m.method_type.slice(1).toLowerCase() },
          { id: "ref", header: "Needs reference", cell: (m) => (m.requires_reference ? "Yes" : "No"), hideOnMobile: true },
          { id: "st", header: "Status", cell: (m) => <StatusBadge status={m.is_active ? "ACTIVE" : "INACTIVE"} /> },
          { id: "a", header: <span className="sr-only">Actions</span>, align: "right", cell: (m) => editable ? <Button variant="ghost" size="icon-sm" aria-label={`Edit ${m.name}`} onClick={() => setDialog(m)}><Pencil className="size-4" /></Button> : null },
        ]} />
      <FormDialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)} title={editing ? "Edit payment method" : "New payment method"} size="sm">
        <form onSubmit={handleSubmit(async (v) => { setServerError(null); try { await save.mutateAsync(v) } catch (e) { setServerError((e as Error).message) } })} className="space-y-4" noValidate>
          <ErrorBox msg={serverError} />
          <Field label="Name" required error={errors.name?.message}>{(p) => <Input {...p} autoFocus {...register("name")} />}</Field>
          <Field label="Code" required error={errors.code?.message} hint="Short unique code, e.g. UPAY">{(p) => <Input {...p} disabled={!!editing} className="font-mono uppercase" {...register("code")} />}</Field>
          <Field label="Type">{(p) => <NativeSelect {...p} {...register("method_type")}><option value="CASH">Cash</option><option value="CARD">Card</option><option value="MOBILE">Mobile banking</option><option value="BANK">Bank transfer</option><option value="OTHER">Other</option></NativeSelect>}</Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" {...register("requires_reference")} /> Require a reference / transaction ID</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" {...register("is_active")} /> Active</label>
          <SubmitRow onCancel={() => setDialog(null)} submitting={save.isPending} />
        </form>
      </FormDialog>
    </>
  )
}

/* ---------------------------------- units ---------------------------------- */

const unitSchema = z.object({ name: z.string().trim().min(1, "Name is required").max(50), short_name: z.string().trim().min(1, "Short name is required").max(15), allow_decimal: z.boolean(), is_active: z.boolean() })
type UnitValues = z.infer<typeof unitSchema>

export function UnitSettings() {
  const { can } = useAuth()
  const { data, isLoading, error, refetch } = useUnits()
  const [dialog, setDialog] = useState<Unit | "new" | null>(null)
  const editing = dialog && dialog !== "new" ? dialog : null
  const [serverError, setServerError] = useState<string | null>(null)
  const { register, handleSubmit, formState: { errors } } = useForm<UnitValues>({ resolver: zodResolver(unitSchema), values: editing ? { name: editing.name, short_name: editing.short_name, allow_decimal: editing.allow_decimal, is_active: editing.is_active } : { name: "", short_name: "", allow_decimal: false, is_active: true } })
  const save = useApiMutation((v: UnitValues) => (editing ? api.put(`/units/${editing.id}`, v) : api.post("/units", v)), { success: "Unit saved", invalidate: [["units"]], onSuccess: () => setDialog(null), silentError: true })
  const editable = can("category.manage")
  return (
    <>
      <Toolbar2 title="Units of measure" description="Weighed and measured units allow fractional quantities at the POS." onAdd={editable ? () => setDialog("new") : undefined} addLabel="Add unit" />
      <DataTable<Unit> page={listPage(data)} isLoading={isLoading} error={error} onRetry={() => refetch()} rowKey={(u) => u.id} empty={{ title: "No units." }}
        columns={[
          { id: "name", header: "Unit", cell: (u) => <span className="font-medium">{u.name}</span> },
          { id: "short", header: "Short", cell: (u) => u.short_name },
          { id: "dec", header: "Fractions", cell: (u) => (u.allow_decimal ? "Allowed (e.g. 1.5 kg)" : "Whole numbers only") },
          { id: "st", header: "Status", cell: (u) => <StatusBadge status={u.is_active ? "ACTIVE" : "INACTIVE"} />, hideOnMobile: true },
          { id: "a", header: <span className="sr-only">Actions</span>, align: "right", cell: (u) => editable ? <Button variant="ghost" size="icon-sm" aria-label={`Edit ${u.name}`} onClick={() => setDialog(u)}><Pencil className="size-4" /></Button> : null },
        ]} />
      <FormDialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)} title={editing ? "Edit unit" : "New unit"} size="sm">
        <form onSubmit={handleSubmit(async (v) => { setServerError(null); try { await save.mutateAsync(v) } catch (e) { setServerError((e as Error).message) } })} className="space-y-4" noValidate>
          <ErrorBox msg={serverError} />
          <Field label="Name" required error={errors.name?.message}>{(p) => <Input {...p} autoFocus {...register("name")} />}</Field>
          <Field label="Short name" required error={errors.short_name?.message}>{(p) => <Input {...p} {...register("short_name")} />}</Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" {...register("allow_decimal")} /> Allow fractional quantities</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" {...register("is_active")} /> Active</label>
          <SubmitRow onCancel={() => setDialog(null)} submitting={save.isPending} />
        </form>
      </FormDialog>
    </>
  )
}

/* ------------------------------- promotions ------------------------------- */

const TYPE_LABEL: Record<string, string> = { BUY_X_GET_Y: "Buy X get Y free", PERCENT_OFF: "Percentage off product", FIXED_OFF: "Fixed amount off product", CATEGORY_PERCENT: "Percentage off category" }
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

export function PromotionSettings() {
  const { can } = useAuth()
  const manage = can("promotion.manage")
  const promos = useQuery({ queryKey: ["promotions"], queryFn: () => api.get<Promotion[]>("/promotions") })
  const discounts = useQuery({ queryKey: ["discounts"], queryFn: () => api.get<Discount[]>("/discounts") })
  const cats = useCategories()
  const [open, setOpen] = useState(false)
  const [discOpen, setDiscOpen] = useState(false)
  const [del, setDel] = useState<Promotion | null>(null)

  const [f, setF] = useState({ name: "", promo_type: "PERCENT_OFF", value: "10", buy: "2", get: "1", category_id: "", days: [] as number[], start_time: "", end_time: "", start_at: "", end_at: "" })
  const [product, setProduct] = useState<Option | null>(null)
  const [error, setError] = useState<string | null>(null)
  const create = useApiMutation(
    () => api.post("/promotions", {
      name: f.name, promo_type: f.promo_type, product_id: f.promo_type !== "CATEGORY_PERCENT" ? product?.id : undefined, category_id: f.promo_type === "CATEGORY_PERCENT" ? Number(f.category_id) : undefined,
      value: f.promo_type === "BUY_X_GET_Y" ? 0 : Number(f.value), buy_quantity: Number(f.buy), get_quantity: Number(f.get),
      days_of_week: f.days.length ? f.days.sort().join(",") : undefined, start_time: f.start_time || undefined, end_time: f.end_time || undefined,
      start_at: f.start_at ? new Date(f.start_at).toISOString() : undefined, end_at: f.end_at ? new Date(f.end_at).toISOString() : undefined,
    }),
    { success: "Promotion created", invalidate: [["promotions"], ["pos-preview"]], onSuccess: () => { setOpen(false); setF({ ...f, name: "" }); setProduct(null) }, silentError: true },
  )
  const remove = useApiMutation((p: Promotion) => api.delete(`/promotions/${p.id}`), { success: "Promotion deactivated", invalidate: [["promotions"]] })
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(null)
    if (!f.name.trim()) return setError("Give the promotion a name.")
    if (f.promo_type === "CATEGORY_PERCENT" ? !f.category_id : !product) return setError(f.promo_type === "CATEGORY_PERCENT" ? "Choose a category." : "Choose a product.")
    try { await create.mutateAsync() } catch (err) { setError((err as Error).message) }
  }
  const describe = (p: Promotion) => {
    const when = [p.days_of_week ? p.days_of_week.split(",").map((d) => DAYS[Number(d)]).join("/") : null, p.start_time && p.end_time ? `${p.start_time}–${p.end_time}` : null, p.end_at ? `until ${formatDateTime(p.end_at)}` : null].filter(Boolean).join(" · ")
    const what = p.promo_type === "BUY_X_GET_Y" ? `Buy ${formatNumber(p.buy_quantity)} get ${formatNumber(p.get_quantity)} free` : p.promo_type === "FIXED_OFF" ? `৳${p.value} off each` : `${p.value}% off`
    return `${what}${when ? ` · ${when}` : ""}`
  }
  return (
    <>
      <Toolbar2 title="Promotions" description="Applied automatically at the POS when their time window matches (Bangladesh time). The best automatic discount wins — offers don’t stack with a product’s standing discount." onAdd={manage ? () => setOpen(true) : undefined} addLabel="New promotion" />
      <DataTable<Promotion> page={listPage(promos.data)} isLoading={promos.isLoading} error={promos.error} onRetry={() => promos.refetch()} rowKey={(p) => p.id} empty={{ title: "No promotions yet.", description: "Create e.g. ‘Friday 5–9 PM: Dairy 10% off’." }}
        columns={[
          { id: "n", header: "Promotion", cell: (p) => <div><div className="font-medium">{p.name}</div><div className="text-xs text-muted-foreground">{TYPE_LABEL[p.promo_type]}</div></div> },
          { id: "d", header: "Offer", cell: (p) => describe(p), hideOnMobile: true },
          { id: "s", header: "Status", cell: (p) => <StatusBadge status={p.is_active ? "ACTIVE" : "INACTIVE"} /> },
          { id: "a", header: <span className="sr-only">Actions</span>, align: "right", cell: (p) => manage && p.is_active ? <Button variant="ghost" size="icon-sm" aria-label={`Deactivate ${p.name}`} onClick={() => setDel(p)}><Trash2 className="size-4" /></Button> : null },
        ]} />
      <div className="mt-8"><Toolbar2 title="Discount presets" description="Quick discounts a cashier can pick. Presets flagged ‘approval’ need a manager." onAdd={manage ? () => setDiscOpen(true) : undefined} addLabel="Add preset" /></div>
      <DataTable<Discount> page={listPage(discounts.data)} isLoading={discounts.isLoading} rowKey={(d) => d.id} empty={{ title: "No discount presets." }}
        columns={[
          { id: "n", header: "Name", cell: (d) => <span className="font-medium">{d.name}</span> }, { id: "c", header: "Code", cell: (d) => d.code ?? "—", hideOnMobile: true },
          { id: "v", header: "Value", align: "right", cell: (d) => (d.discount_type === "PERCENT" ? `${d.value}%` : <Money value={d.value} />) },
          { id: "ap", header: "Approval", cell: (d) => (d.requires_approval ? "Manager" : "None"), hideOnMobile: true },
        ]} />
      <DiscountPresetDialog open={discOpen} onClose={() => setDiscOpen(false)} />
      <FormDialog open={open} onOpenChange={setOpen} title="New promotion" size="lg">
        <form onSubmit={submit} className="space-y-4" noValidate>
          <ErrorBox msg={error} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" required className="sm:col-span-2">{(p) => <Input {...p} autoFocus value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}</Field>
            <Field label="Type">{(p) => <NativeSelect {...p} value={f.promo_type} onChange={(e) => setF({ ...f, promo_type: e.target.value })}>{Object.entries(TYPE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect>}</Field>
            {f.promo_type === "CATEGORY_PERCENT"
              ? <Field label="Category" required>{(p) => <NativeSelect {...p} value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })}><option value="">Select…</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect>}</Field>
              : <Field label="Product" required>{(p) => <AsyncCombobox id={p.id} value={product} onChange={setProduct} fetcher={searchProducts} queryKey="products" placeholder="Search product…" />}</Field>}
            {f.promo_type === "BUY_X_GET_Y" ? (<><Field label="Buy quantity">{(p) => <Input {...p} type="number" min="1" value={f.buy} onChange={(e) => setF({ ...f, buy: e.target.value })} />}</Field><Field label="Get free">{(p) => <Input {...p} type="number" min="1" value={f.get} onChange={(e) => setF({ ...f, get: e.target.value })} />}</Field></>)
              : <Field label={f.promo_type === "FIXED_OFF" ? "Amount off (৳)" : "Percent off (%)"}>{(p) => <Input {...p} type="number" min="0" step="0.01" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} />}</Field>}
            <Field label="Valid from (optional)">{(p) => <Input {...p} type="datetime-local" value={f.start_at} onChange={(e) => setF({ ...f, start_at: e.target.value })} />}</Field>
            <Field label="Valid until (optional)">{(p) => <Input {...p} type="datetime-local" value={f.end_at} onChange={(e) => setF({ ...f, end_at: e.target.value })} />}</Field>
            <Field label="From time of day">{(p) => <Input {...p} type="time" value={f.start_time} onChange={(e) => setF({ ...f, start_time: e.target.value })} />}</Field>
            <Field label="Until time of day">{(p) => <Input {...p} type="time" value={f.end_time} onChange={(e) => setF({ ...f, end_time: e.target.value })} />}</Field>
          </div>
          <fieldset><legend className="mb-1.5 text-[13px] font-medium">Days (none = every day)</legend>
            <div className="flex flex-wrap gap-2">{DAYS.map((d, i) => <label key={d} className="flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm"><Checkbox checked={f.days.includes(i)} onCheckedChange={(c) => setF({ ...f, days: c ? [...f.days, i] : f.days.filter((x) => x !== i) })} />{d}</label>)}</div>
          </fieldset>
          <SubmitRow onCancel={() => setOpen(false)} submitting={create.isPending} submitLabel="Create promotion" />
        </form>
      </FormDialog>
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Deactivate “${del?.name}”?`} description="It stops applying immediately. Past sales keep their discounts." confirmLabel="Deactivate" destructive onConfirm={() => remove.mutateAsync(del!)} />
    </>
  )
}

function DiscountPresetDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("")
  const [type, setType] = useState("PERCENT")
  const [value, setValue] = useState("")
  const [approval, setApproval] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const create = useApiMutation(() => api.post("/discounts", { name, discount_type: type, value: Number(value), requires_approval: approval }), { success: "Preset added", invalidate: [["discounts"]], onSuccess: () => { setName(""); setValue(""); onClose() }, silentError: true })
  async function submit(e: React.FormEvent) { e.preventDefault(); setError(null); if (!name.trim() || !(Number(value) > 0)) return setError("Enter a name and a value greater than zero."); try { await create.mutateAsync() } catch (err) { setError((err as Error).message) } }
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title="New discount preset" size="sm">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <ErrorBox msg={error} />
        <Field label="Name" required>{(p) => <Input {...p} autoFocus value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        <div className="grid grid-cols-2 gap-3"><Field label="Type">{(p) => <NativeSelect {...p} value={type} onChange={(e) => setType(e.target.value)}><option value="PERCENT">Percent</option><option value="FIXED">Fixed ৳</option></NativeSelect>}</Field><Field label="Value" required>{(p) => <Input {...p} type="number" min="0" step="0.01" value={value} onChange={(e) => setValue(e.target.value)} />}</Field></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" checked={approval} onChange={(e) => setApproval(e.target.checked)} /> Needs manager approval</label>
        <SubmitRow onCancel={onClose} submitting={create.isPending} />
      </form>
    </FormDialog>
  )
}

