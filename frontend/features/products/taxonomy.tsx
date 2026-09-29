"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { DataTable } from "@/components/shared/data-table"
import { ConfirmDialog, FormDialog, SubmitRow } from "@/components/shared/dialogs"
import { Can, Field, NativeSelect, PageHeader, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { optionalNumber, useBrands, useCategories } from "@/services/lookups"
import type { Brand, Category } from "@/types/api"

/* ------------------------------ categories ------------------------------ */

const catSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(100),
  name_bn: z.string().trim().max(100).optional(),
  parent_id: z.number().optional(),
  is_active: z.boolean(),
})
type CatValues = z.infer<typeof catSchema>

function CategoryDialog({ category, categories, onClose }: { category: Category | "new" | null; categories: Category[]; onClose: () => void }) {
  const editing = category && category !== "new" ? category : null
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<CatValues>({
    resolver: zodResolver(catSchema),
    values: editing ? { name: editing.name, name_bn: editing.name_bn ?? "", parent_id: editing.parent_id ?? undefined, is_active: editing.is_active } : { name: "", name_bn: "", parent_id: undefined, is_active: true },
  })
  const save = useApiMutation(
    (v: CatValues) => { const body = { ...v, parent_id: v.parent_id ?? null, name_bn: v.name_bn || null }; return editing ? api.put(`/categories/${editing.id}`, body) : api.post("/categories", body) },
    { success: "Category saved", invalidate: [["categories"], ["products"]], onSuccess: onClose },
  )
  return (
    <FormDialog open={!!category} onOpenChange={(o) => !o && onClose()} title={editing ? "Edit category" : "New category"}>
      <form onSubmit={handleSubmit((v) => save.mutate(v))} className="space-y-4" noValidate>
        <Field label="Name" required error={errors.name?.message}>{(p) => <Input {...p} autoFocus {...register("name")} />}</Field>
        <Field label="Bangla name">{(p) => <Input {...p} lang="bn" {...register("name_bn")} />}</Field>
        <Field label="Parent category" hint="Leave empty for a top-level category">
          {(p) => (
            <NativeSelect {...p} {...register("parent_id", { setValueAs: optionalNumber })}>
              <option value="">— Top level —</option>
              {categories.filter((c) => c.parent_id === null && c.id !== editing?.id).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </NativeSelect>
          )}
        </Field>
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={watch("is_active")} onCheckedChange={(c) => setValue("is_active", !!c)} /> Active</label>
        <SubmitRow onCancel={onClose} submitting={save.isPending} />
      </form>
    </FormDialog>
  )
}

export function CategoriesPage() {
  const { can } = useAuth()
  const { data = [], isLoading, error, refetch } = useCategories(true)
  const [dialog, setDialog] = useState<Category | "new" | null>(null)
  const [del, setDel] = useState<Category | null>(null)
  const remove = useApiMutation((c: Category) => api.delete(`/categories/${c.id}`), { success: "Category deleted", invalidate: [["categories"]] })
  const parentName = (id: number | null) => data.find((c) => c.id === id)?.name
  const rows = [...data].sort((a, b) => (parentName(a.parent_id) ?? a.name).localeCompare(parentName(b.parent_id) ?? b.name) || (a.parent_id ? 1 : -1))
  const manage = can("category.manage")

  return (
    <>
      <PageHeader title="Categories" description="Organise products into categories and sub-categories."
        actions={<Can perm="category.manage"><Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add category</Button></Can>} />
      <DataTable<Category>
        page={{ items: rows, total: rows.length, page: 1, page_size: rows.length || 1, pages: 1 }}
        isLoading={isLoading} error={error} onRetry={() => refetch()} rowKey={(c) => c.id}
        empty={{ title: "No categories yet.", description: "Create categories such as Grocery, Dairy or Beverage.", action: manage ? <Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add category</Button> : undefined }}
        columns={[
          { id: "name", header: "Name", cell: (c) => <span className={c.parent_id ? "pl-6 text-muted-foreground" : "font-medium"}>{c.parent_id && "↳ "}{c.name}</span> },
          { id: "bn", header: "Bangla", cell: (c) => <span lang="bn">{c.name_bn ?? "—"}</span>, hideOnMobile: true },
          { id: "parent", header: "Parent", cell: (c) => parentName(c.parent_id) ?? "—", hideOnMobile: true },
          { id: "status", header: "Status", cell: (c) => <StatusBadge status={c.is_active ? "ACTIVE" : "INACTIVE"} /> },
          { id: "actions", header: <span className="sr-only">Actions</span>, align: "right", cell: (c) => manage ? (
            <div className="flex justify-end gap-1">
              <Button variant="ghost" size="icon-sm" aria-label={`Edit ${c.name}`} onClick={() => setDialog(c)}><Pencil className="size-4" /></Button>
              <Button variant="ghost" size="icon-sm" aria-label={`Delete ${c.name}`} onClick={() => setDel(c)}><Trash2 className="size-4" /></Button>
            </div>) : null },
        ]}
      />
      <CategoryDialog category={dialog} categories={data} onClose={() => setDialog(null)} />
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete ${del?.name}?`} description="Categories that still contain products or sub-categories cannot be deleted." confirmLabel="Delete" destructive onConfirm={() => remove.mutateAsync(del!)} />
    </>
  )
}

/* -------------------------------- brands -------------------------------- */

const brandSchema = z.object({ name: z.string().trim().min(1, "Name is required").max(100), is_active: z.boolean() })
type BrandValues = z.infer<typeof brandSchema>

export function BrandsPage() {
  const { can } = useAuth()
  const { data = [], isLoading, error, refetch } = useBrands()
  const [dialog, setDialog] = useState<Brand | "new" | null>(null)
  const [del, setDel] = useState<Brand | null>(null)
  const editing = dialog && dialog !== "new" ? dialog : null
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<BrandValues>({
    resolver: zodResolver(brandSchema), values: editing ? { name: editing.name, is_active: editing.is_active } : { name: "", is_active: true },
  })
  const save = useApiMutation((v: BrandValues) => (editing ? api.put(`/brands/${editing.id}`, v) : api.post("/brands", v)), { success: "Brand saved", invalidate: [["brands"]], onSuccess: () => setDialog(null) })
  const remove = useApiMutation((b: Brand) => api.delete(`/brands/${b.id}`), { success: "Brand deleted", invalidate: [["brands"]] })
  const manage = can("category.manage")
  return (
    <>
      <PageHeader title="Brands" description="Brands help with filtering and reporting."
        actions={<Can perm="category.manage"><Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add brand</Button></Can>} />
      <DataTable<Brand>
        page={{ items: data, total: data.length, page: 1, page_size: data.length || 1, pages: 1 }}
        isLoading={isLoading} error={error} onRetry={() => refetch()} rowKey={(b) => b.id}
        empty={{ title: "No brands yet.", action: manage ? <Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add brand</Button> : undefined }}
        columns={[
          { id: "name", header: "Brand", cell: (b) => <span className="font-medium">{b.name}</span> },
          { id: "status", header: "Status", cell: (b) => <StatusBadge status={b.is_active ? "ACTIVE" : "INACTIVE"} /> },
          { id: "actions", header: <span className="sr-only">Actions</span>, align: "right", cell: (b) => manage ? (
            <div className="flex justify-end gap-1">
              <Button variant="ghost" size="icon-sm" aria-label={`Edit ${b.name}`} onClick={() => setDialog(b)}><Pencil className="size-4" /></Button>
              <Button variant="ghost" size="icon-sm" aria-label={`Delete ${b.name}`} onClick={() => setDel(b)}><Trash2 className="size-4" /></Button>
            </div>) : null },
        ]}
      />
      <FormDialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)} title={editing ? "Edit brand" : "New brand"} size="sm">
        <form onSubmit={handleSubmit((v) => save.mutate(v))} className="space-y-4" noValidate>
          <Field label="Name" required error={errors.name?.message}>{(p) => <Input {...p} autoFocus {...register("name")} />}</Field>
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={watch("is_active")} onCheckedChange={(c) => setValue("is_active", !!c)} /> Active</label>
          <SubmitRow onCancel={() => setDialog(null)} submitting={save.isPending} />
        </form>
      </FormDialog>
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete ${del?.name}?`} description="Brands used by products cannot be deleted." confirmLabel="Delete" destructive onConfirm={() => remove.mutateAsync(del!)} />
    </>
  )
}
