"use client"

import { Plus, Trash2, Upload } from "lucide-react"
import Image from "next/image"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { ConfirmDialog } from "@/components/shared/dialogs"
import { Can, Money, NativeSelect, PageHeader, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api, mediaUrl } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatNumber } from "@/lib/format"
import { useT } from "@/lib/i18n"
import { useBrands, useCategories } from "@/services/lookups"
import type { Product } from "@/types/api"

export function ProductsList() {
  const t = useT()
  const router = useRouter()
  const { can } = useAuth()
  const [category, setCategory] = useState("")
  const [brand, setBrand] = useState("")
  const [stock, setStock] = useState("")
  const [active, setActive] = useState("")
  const [toDelete, setToDelete] = useState<Product | null>(null)
  const cats = useCategories()
  const brands = useBrands()

  const { query, data, page, setPage, search, setSearch, sort, toggleSort } = useTableQuery<Product>("products", "/products", {
    filters: { category_id: category || undefined, brand_id: brand || undefined, stock_status: stock || undefined, is_active: active || undefined },
    defaultSort: "name",
  })

  const remove = useApiMutation((p: Product) => api.delete(`/products/${p.id}`), { success: "Product deleted", invalidate: [["products"]] })

  const showCost = can("product.cost")
  return (
    <>
      <PageHeader
        title={t("nav.products.all")}
        description="Manage your catalogue, prices and stock rules."
        actions={
          <>
            <Can perm="product.import"><Button variant="outline" render={<Link href="/settings?tab=import" />}><Upload className="size-4" /> Import CSV</Button></Can>
            <Can perm="product.create"><Button render={<Link href="/products/new" />}><Plus className="size-4" /> Add product</Button></Can>
          </>
        }
      />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search name, SKU or barcode…" />
        <NativeSelect aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} className="w-44">
          <option value="">All categories</option>{cats.data?.filter((c) => c.parent_id === null).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </NativeSelect>
        <NativeSelect aria-label="Brand" value={brand} onChange={(e) => setBrand(e.target.value)} className="w-40">
          <option value="">All brands</option>{brands.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </NativeSelect>
        <NativeSelect aria-label="Stock level" value={stock} onChange={(e) => setStock(e.target.value)} className="w-40">
          <option value="">Any stock</option><option value="in">In stock</option><option value="low">Low stock</option><option value="out">Out of stock</option>
        </NativeSelect>
        <NativeSelect aria-label="Status" value={active} onChange={(e) => setActive(e.target.value)} className="w-32">
          <option value="">All</option><option value="true">Active</option><option value="false">Inactive</option>
        </NativeSelect>
      </Toolbar>

      <DataTable<Product>
        caption="Products"
        page={data}
        isLoading={query.isLoading}
        isFetching={query.isFetching}
        error={query.error}
        onRetry={() => query.refetch()}
        onPageChange={setPage}
        sort={sort}
        onSort={toggleSort}
        rowKey={(p) => p.id}
        onRowClick={(p) => router.push(`/products/${p.id}`)}
        empty={{
          title: search ? "No products match your search" : "No products found.",
          description: search ? "Try a different name, SKU or barcode." : "Add your first product to start selling and tracking stock.",
          action: can("product.create") && !search ? <Button render={<Link href="/products/new" />}><Plus className="size-4" /> Add product</Button> : undefined,
        }}
        columns={[
          {
            id: "name", header: "Product", sortKey: "name",
            cell: (p) => (
              <div className="flex items-center gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted text-xs font-semibold text-muted-foreground">
                  {p.image_path ? <Image src={mediaUrl(p.image_path)!} alt="" width={40} height={40} className="size-full object-cover" unoptimized /> : p.name.slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0"><div className="truncate font-medium">{p.name}</div>{p.name_bn && <div className="truncate text-xs text-muted-foreground" lang="bn">{p.name_bn}</div>}</div>
              </div>
            ),
          },
          { id: "sku", header: "SKU", sortKey: "sku", cell: (p) => <span className="font-mono text-xs">{p.sku}</span>, hideOnMobile: true },
          { id: "barcode", header: "Barcode", cell: (p) => <span className="font-mono text-xs text-muted-foreground">{p.barcode ?? "—"}</span>, hideOnMobile: true },
          { id: "category", header: "Category", cell: (p) => p.category?.name ?? "—", hideOnMobile: true },
          ...(showCost ? [{ id: "cost", header: "Cost", align: "right" as const, cell: (p: Product) => <Money value={p.purchase_price} className="text-muted-foreground" />, hideOnMobile: true }] : []),
          { id: "price", header: "Price", sortKey: "selling_price", align: "right", cell: (p) => <Money value={p.selling_price} className="font-medium" /> },
          {
            id: "stock", header: "Stock", align: "right",
            cell: (p) => (
              <div className="flex items-center justify-end gap-2">
                <span className="tabular">{formatNumber(p.current_stock)} <span className="text-xs text-muted-foreground">{p.unit.short_name}</span></span>
                {p.current_stock <= 0 ? <StatusBadge status="out" /> : p.current_stock <= p.reorder_level ? <StatusBadge status="low" /> : null}
              </div>
            ),
          },
          { id: "status", header: "Status", cell: (p) => <StatusBadge status={p.is_active ? "ACTIVE" : "INACTIVE"} />, hideOnMobile: true },
          {
            id: "actions", header: <span className="sr-only">Actions</span>, align: "right",
            cell: (p) => can("product.delete") ? (
              <Button variant="ghost" size="icon-sm" aria-label={`Delete ${p.name}`} onClick={(e) => { e.stopPropagation(); setToDelete(p) }}><Trash2 className="size-4 text-muted-foreground" /></Button>
            ) : null,
          },
        ]}
      />

      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`Delete ${toDelete?.name}?`}
        description="The product is archived and hidden from sales. Products that still have stock cannot be deleted — adjust the stock to zero first. Sales history is kept."
        confirmLabel="Delete product"
        destructive
        onConfirm={() => remove.mutateAsync(toDelete!)}
      />
    </>
  )
}
