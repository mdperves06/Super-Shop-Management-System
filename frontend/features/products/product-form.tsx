"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Loader2, RefreshCw } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { AsyncCombobox, type Option } from "@/components/shared/combobox"
import { Field, NativeSelect, SectionCard } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { optionalNumber, searchSuppliers, useBrands, useCategories, useTaxRates, useUnits } from "@/services/lookups"
import type { Product } from "@/types/api"

const num = z.number({ error: "Enter a number" })
const money = num.min(0, "Cannot be negative").max(99999999, "Too large")

const schema = z
  .object({
    sku: z.string().trim().min(1, "SKU is required").max(60),
    barcode: z.string().trim().max(64).optional(),
    name: z.string().trim().min(1, "Name is required").max(200),
    name_bn: z.string().trim().max(200).optional(),
    description: z.string().max(2000).optional(),
    category_id: z.number().optional(),
    subcategory_id: z.number().optional(),
    brand_id: z.number().optional(),
    unit_id: z.number({ error: "Choose a unit" }),
    purchase_price: money.optional(),
    selling_price: money,
    mrp: money.optional(),
    tax_rate_id: z.number().optional(),
    discount_percent: num.min(0).max(100).optional(),
    min_stock: num.min(0, "Cannot be negative").optional(),
    max_stock: num.min(0, "Cannot be negative").optional(),
    reorder_level: num.min(0, "Cannot be negative").optional(),
    track_expiry: z.boolean(),
    track_batch: z.boolean(),
    is_active: z.boolean(),
  })
  .refine((v) => v.max_stock === undefined || v.min_stock === undefined || v.max_stock >= v.min_stock, { path: ["max_stock"], message: "Max stock must be at least the minimum" })

type Values = z.infer<typeof schema>

function toDefaults(p?: Product): Partial<Values> {
  if (!p) return { track_expiry: false, track_batch: false, is_active: true, discount_percent: 0, reorder_level: 0, min_stock: 0, purchase_price: 0 }
  return {
    sku: p.sku, barcode: p.barcode ?? "", name: p.name, name_bn: p.name_bn ?? "", description: p.description ?? "",
    category_id: p.category?.id, subcategory_id: p.subcategory?.id, brand_id: p.brand?.id, unit_id: p.unit.id,
    purchase_price: p.purchase_price ?? undefined, selling_price: p.selling_price, mrp: p.mrp ?? undefined, tax_rate_id: p.tax_rate?.id,
    discount_percent: p.discount_percent, min_stock: p.min_stock, max_stock: p.max_stock ?? undefined, reorder_level: p.reorder_level,
    track_expiry: p.track_expiry, track_batch: p.track_batch, is_active: p.is_active,
  }
}

export function ProductForm({ product }: { product?: Product }) {
  const router = useRouter()
  const { can } = useAuth()
  const canCost = can("product.cost")
  const cats = useCategories()
  const brands = useBrands()
  const units = useUnits()
  const taxes = useTaxRates()
  const [supplier, setSupplier] = useState<Option | null>(null)
  const [generating, setGenerating] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toDefaults(product) })

  const parents = (cats.data ?? []).filter((c) => c.parent_id === null)
  const categoryId = watch("category_id")
  const children = (cats.data ?? []).filter((c) => c.parent_id !== null && c.parent_id === categoryId)
  const unitId = watch("unit_id")
  const decimalUnit = units.data?.find((u) => u.id === unitId)?.allow_decimal

  const save = useApiMutation(
    async (v: Values) => {
      const body: Record<string, unknown> = { ...v, supplier_id: supplier?.id ?? product?.supplier_id ?? null }
      for (const k of Object.keys(body)) if (body[k] === "" || body[k] === undefined) body[k] = k === "barcode" ? undefined : null
      if (!canCost) delete body.purchase_price
      if (product) return api.patch<Product>(`/products/${product.id}`, body)
      return api.post<Product>("/products", body)
    },
    {
      success: (p) => `${p.name} saved`,
      invalidate: [["products"], ["stock"]],
      onSuccess: (p) => router.push(`/products/${p.id}`),
      silentError: true,
    },
  )

  async function generate() {
    setGenerating(true)
    try {
      const r = await api.get<{ barcode: string }>("/products/generate-barcode")
      setValue("barcode", r.barcode, { shouldDirty: true })
    } catch { toast.error("Could not generate a barcode") } finally { setGenerating(false) }
  }

  async function onSubmit(v: Values) {
    setServerError(null)
    try { await save.mutateAsync(v) } catch (e) { setServerError((e as Error).message) }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {serverError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{serverError}</div>}

      <SectionCard title="Basic information">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Product name" required error={errors.name?.message}>{(p) => <Input {...p} {...register("name")} />}</Field>
          <Field label="Bangla name" error={errors.name_bn?.message}>{(p) => <Input {...p} lang="bn" {...register("name_bn")} />}</Field>
          <Field label="SKU" required error={errors.sku?.message} hint="Must be unique">{(p) => <Input {...p} className="font-mono" {...register("sku")} />}</Field>
          <Field label="Barcode" error={errors.barcode?.message} hint="Scan with a USB scanner or type it. Leave empty to add later.">
            {(p) => (
              <div className="flex gap-2">
                <Input {...p} className="font-mono" inputMode="numeric" {...register("barcode")} />
                <Button type="button" variant="outline" onClick={generate} disabled={generating} aria-label="Generate barcode">
                  {generating ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}<span className="hidden sm:inline">Generate</span>
                </Button>
              </div>
            )}
          </Field>
          <Field label="Category" error={errors.category_id?.message}>
            {(p) => (
              <NativeSelect {...p} {...register("category_id", { setValueAs: optionalNumber, onChange: () => setValue("subcategory_id", undefined) })}>
                <option value="">— None —</option>{parents.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </NativeSelect>
            )}
          </Field>
          <Field label="Subcategory">
            {(p) => (
              <NativeSelect {...p} disabled={children.length === 0} {...register("subcategory_id", { setValueAs: optionalNumber })}>
                <option value="">— None —</option>{children.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </NativeSelect>
            )}
          </Field>
          <Field label="Brand">
            {(p) => <NativeSelect {...p} {...register("brand_id", { setValueAs: optionalNumber })}><option value="">— None —</option>{brands.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</NativeSelect>}
          </Field>
          <Field label="Unit" required error={errors.unit_id?.message} hint={decimalUnit ? "Sold by weight/volume — fractions allowed" : undefined}>
            {(p) => <NativeSelect {...p} {...register("unit_id", { setValueAs: optionalNumber })}><option value="">Select unit…</option>{units.data?.map((u) => <option key={u.id} value={u.id}>{u.name} ({u.short_name})</option>)}</NativeSelect>}
          </Field>
          <Field label="Default supplier">
            {(p) => <AsyncCombobox id={p.id} value={supplier ?? (product?.supplier_id ? { id: product.supplier_id, label: `Supplier #${product.supplier_id}` } : null)} onChange={setSupplier} fetcher={searchSuppliers} queryKey="suppliers" placeholder="Choose supplier…" />}
          </Field>
          <Field label="Description" className="md:col-span-2" error={errors.description?.message}>{(p) => <Textarea {...p} rows={2} {...register("description")} />}</Field>
        </div>
      </SectionCard>

      <SectionCard title="Pricing & tax" description="VAT is configured under Settings → Tax. Whether shelf prices include VAT is also a setting.">
        <div className="grid gap-4 md:grid-cols-3">
          {canCost && <Field label="Purchase price (cost)" error={errors.purchase_price?.message}>{(p) => <Input {...p} type="number" step="0.01" min="0" inputMode="decimal" {...register("purchase_price", { setValueAs: optionalNumber })} />}</Field>}
          <Field label="Selling price" required error={errors.selling_price?.message}>{(p) => <Input {...p} type="number" step="0.01" min="0" inputMode="decimal" {...register("selling_price", { setValueAs: optionalNumber })} />}</Field>
          <Field label="MRP" error={errors.mrp?.message}>{(p) => <Input {...p} type="number" step="0.01" min="0" inputMode="decimal" {...register("mrp", { setValueAs: optionalNumber })} />}</Field>
          <Field label="VAT / tax rate">
            {(p) => <NativeSelect {...p} {...register("tax_rate_id", { setValueAs: optionalNumber })}><option value="">No tax</option>{taxes.data?.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.name} ({t.rate}%)</option>)}</NativeSelect>}
          </Field>
          <Field label="Standing discount %" error={errors.discount_percent?.message} hint="Applied automatically at the POS">{(p) => <Input {...p} type="number" step="0.01" min="0" max="100" {...register("discount_percent", { setValueAs: optionalNumber })} />}</Field>
        </div>
      </SectionCard>

      <SectionCard title="Stock rules">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Reorder level" error={errors.reorder_level?.message} hint="Low-stock alert when stock reaches this">{(p) => <Input {...p} type="number" step="any" min="0" {...register("reorder_level", { setValueAs: optionalNumber })} />}</Field>
          <Field label="Minimum stock" error={errors.min_stock?.message}>{(p) => <Input {...p} type="number" step="any" min="0" {...register("min_stock", { setValueAs: optionalNumber })} />}</Field>
          <Field label="Maximum stock" error={errors.max_stock?.message}>{(p) => <Input {...p} type="number" step="any" min="0" {...register("max_stock", { setValueAs: optionalNumber })} />}</Field>
        </div>
        <div className="mt-4 flex flex-wrap gap-x-8 gap-y-3">
          {([["track_expiry", "Track expiry dates (FEFO)"], ["track_batch", "Track batches"], ["is_active", "Active — can be sold"]] as const).map(([name, label]) => (
            <label key={name} className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox checked={watch(name)} onCheckedChange={(c) => setValue(name, !!c, { shouldDirty: true })} />
              {label}
            </label>
          ))}
        </div>
      </SectionCard>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => router.back()}>Cancel</Button>
        <Button type="submit" disabled={save.isPending}>{save.isPending && <Loader2 className="size-4 animate-spin" />}{product ? "Save changes" : "Create product"}</Button>
      </div>
    </form>
  )
}
