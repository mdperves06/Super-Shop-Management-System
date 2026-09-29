"use client"

import { useQuery } from "@tanstack/react-query"
import { Camera, Loader2 } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { Field, NativeSelect, SectionCard } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { api, mediaUrl } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import type { Settings } from "@/types/api"

type FieldDef =
  | { key: string; label: string; type: "text" | "textarea" | "number"; hint?: string; min?: number; max?: number }
  | { key: string; label: string; type: "bool"; hint?: string }
  | { key: string; label: string; type: "select"; options: [string, string][]; hint?: string }

interface Section { title: string; description?: string; fields: FieldDef[] }

const SECTIONS: Section[] = [
  {
    title: "Shop profile", description: "Printed on receipts and invoices.",
    fields: [
      { key: "shop.name", label: "Shop name", type: "text" },
      { key: "shop.phone", label: "Phone", type: "text" },
      { key: "shop.email", label: "Email", type: "text" },
      { key: "shop.bin", label: "BIN / VAT registration no.", type: "text", hint: "Shown on receipts when filled" },
      { key: "shop.address", label: "Address", type: "textarea" },
    ],
  },
  {
    title: "Receipts", description: "Thermal receipts and PDF invoices.",
    fields: [
      { key: "receipt.header", label: "Header line", type: "text", hint: "e.g. a slogan or branch name" },
      { key: "receipt.footer", label: "Footer message", type: "text" },
      { key: "receipt.paper_width_mm", label: "Paper width", type: "select", options: [["58", "58 mm"], ["80", "80 mm"]] },
      { key: "receipt.show_tax", label: "Show VAT line on receipts", type: "bool" },
    ],
  },
  {
    title: "Regional", description: "Currency, time zone and formats.",
    fields: [
      { key: "locale.currency_symbol", label: "Currency symbol", type: "text" },
      { key: "locale.timezone", label: "Time zone", type: "select", options: [["Asia/Dhaka", "Asia/Dhaka (Bangladesh)"], ["Asia/Kolkata", "Asia/Kolkata"], ["Asia/Dubai", "Asia/Dubai"], ["UTC", "UTC"]], hint: "Decides what “today” means in reports" },
      { key: "locale.date_format", label: "Date format", type: "select", options: [["DD/MM/YYYY", "31/12/2026"], ["MM/DD/YYYY", "12/31/2026"], ["YYYY-MM-DD", "2026-12-31"]] },
      { key: "locale.language", label: "Default language", type: "select", options: [["en", "English"], ["bn", "বাংলা (Bangla)"]] },
    ],
  },
  {
    title: "Tax / VAT", description: "Individual rates are managed under the Tax tab.",
    fields: [{ key: "tax.prices_include_tax", label: "Shelf prices already include VAT", type: "bool", hint: "On: VAT is extracted from the selling price (typical for MRP). Off: VAT is added on top." }],
  },
  {
    title: "POS rules",
    fields: [
      { key: "pos.require_open_register", label: "Require an open cash register to sell", type: "bool" },
      { key: "pos.cashier_max_discount_percent", label: "Cashier discount limit (%)", type: "number", min: 0, max: 100, hint: "Larger discounts need the ‘override discounts’ permission (managers)" },
      { key: "pos.loyalty_points_per_100", label: "Loyalty points per ৳100 spent", type: "number", min: 0 },
      { key: "inventory.allow_oversell", label: "Allow selling more than the stock on hand", type: "bool", hint: "Off is strongly recommended — stock can go negative when on." },
      { key: "inventory.allow_expired_sale", label: "Allow selling expired stock", type: "bool" },
    ],
  },
  {
    title: "Inventory alerts",
    fields: [
      { key: "inventory.low_stock_threshold", label: "Default low-stock threshold", type: "number", min: 0, hint: "Products use their own reorder level; this is the fallback." },
      { key: "inventory.expiry_warning_days", label: "Expiry warning window (days)", type: "number", min: 1, max: 730, hint: "Batches expiring within this many days raise alerts" },
      { key: "inventory.valuation_method", label: "Inventory valuation", type: "select", options: [["FIFO", "FIFO batch cost (FEFO for expiry goods)"]], hint: "Every batch keeps the cost it was bought at; stock value and cost of goods use it." },
    ],
  },
  {
    title: "Document numbering", description: "Prefix for invoice / purchase / return numbers, e.g. INV-2026-000001. Letters and digits only.",
    fields: [
      { key: "numbering.invoice_prefix", label: "Invoice prefix", type: "text" },
      { key: "numbering.purchase_prefix", label: "Purchase prefix", type: "text" },
      { key: "numbering.return_prefix", label: "Sale return prefix", type: "text" },
    ],
  },
]

export function GeneralSettings() {
  const { can } = useAuth()
  const editable = can("settings.update")
  const { data, isLoading } = useQuery({ queryKey: ["settings", "all"], queryFn: () => api.get<Settings>("/settings") })
  const [values, setValues] = useState<Settings>({})
  const [error, setError] = useState<string | null>(null)
  const logoRef = useRef<HTMLInputElement>(null)
  useEffect(() => { if (data) setValues(data) }, [data]) // eslint-disable-line react-hooks/set-state-in-effect

  const save = useApiMutation(
    () => {
      const changed: Settings = {}
      for (const s of SECTIONS) for (const f of s.fields) if (values[f.key] !== data?.[f.key]) changed[f.key] = values[f.key]
      return api.put<Settings>("/settings", { values: changed })
    },
    { success: "Settings saved", invalidate: [["settings"]], silentError: true },
  )
  const logo = useApiMutation((file: File) => { const f = new FormData(); f.append("file", file); return api.upload("/settings/logo", f) }, { success: "Logo updated", invalidate: [["settings"]] })

  if (isLoading) return <div className="flex justify-center py-16"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
  const set = (key: string, v: string | number | boolean) => setValues((prev) => ({ ...prev, [key]: v }))

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try { await save.mutateAsync() } catch (err) { setError((err as Error).message) }
  }
  const dirty = data ? SECTIONS.some((s) => s.fields.some((f) => values[f.key] !== data[f.key])) : false

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
      {!editable && <p className="rounded-lg bg-muted px-4 py-2 text-sm text-muted-foreground">You can view settings but not change them.</p>}
      <SectionCard title="Logo" description="Shown on receipts and invoices (PNG, JPG or WebP, up to 5 MB).">
        <div className="flex items-center gap-4">
          <div className="flex size-20 items-center justify-center overflow-hidden rounded-xl border bg-muted text-xs text-muted-foreground">
            {values["shop.logo"] ? <img src={mediaUrl(String(values["shop.logo"]))!} alt="Shop logo" className="size-full object-contain" /> : "No logo"}
          </div>
          {editable && (
            <>
              <input ref={logoRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label="Upload logo" onChange={(e) => { const f = e.target.files?.[0]; if (f) { if (f.size > 5 * 1024 * 1024) toast.error("Logo must be smaller than 5 MB"); else logo.mutate(f, { onSuccess: (r) => set("shop.logo", (r as { path: string }).path) }) } e.target.value = "" }} />
              <Button type="button" variant="outline" onClick={() => logoRef.current?.click()} disabled={logo.isPending}><Camera className="size-4" /> Upload logo</Button>
            </>
          )}
        </div>
      </SectionCard>
      {SECTIONS.map((s) => (
        <SectionCard key={s.title} title={s.title} description={s.description}>
          <div className="grid gap-4 md:grid-cols-2">
            {s.fields.map((f) => (
              <Field key={f.key} label={f.label} hint={f.hint} className={f.type === "textarea" || f.type === "bool" ? "md:col-span-2" : undefined}>
                {(p) =>
                  f.type === "bool" ? (
                    <label className="flex items-center gap-2 text-sm"><Checkbox id={p.id} disabled={!editable} checked={!!values[f.key]} onCheckedChange={(c) => set(f.key, !!c)} /> Enabled</label>
                  ) : f.type === "textarea" ? (
                    <Textarea {...p} rows={2} disabled={!editable} value={String(values[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
                  ) : f.type === "select" ? (
                    <NativeSelect {...p} disabled={!editable} value={String(values[f.key] ?? "")} onChange={(e) => set(f.key, f.key === "receipt.paper_width_mm" ? Number(e.target.value) : e.target.value)}>{f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect>
                  ) : f.type === "number" ? (
                    <Input {...p} type="number" min={f.min} max={f.max} step="any" disabled={!editable} value={String(values[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value === "" ? 0 : Number(e.target.value))} />
                  ) : (
                    <Input {...p} disabled={!editable} value={String(values[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
                  )
                }
              </Field>
            ))}
          </div>
        </SectionCard>
      ))}
      {editable && (
        <div className="sticky bottom-0 -mx-1 flex justify-end gap-2 border-t bg-background/95 p-3 backdrop-blur">
          <Button type="button" variant="outline" disabled={!dirty} onClick={() => data && setValues(data)}>Discard changes</Button>
          <Button type="submit" disabled={!dirty || save.isPending}>{save.isPending && <Loader2 className="size-4 animate-spin" />}Save settings</Button>
        </div>
      )}
    </form>
  )
}
