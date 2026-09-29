"use client"

import { useQuery } from "@tanstack/react-query"
import { Camera, Plus, Trash2 } from "lucide-react"
import Image from "next/image"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { DataTable } from "@/components/shared/data-table"
import { PageLoading, KeyValue, Money, PageHeader, SectionCard, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ProductForm } from "@/features/products/product-form"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { ApiError, api, errorMessage, mediaUrl } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDate, formatDateTime, formatNumber } from "@/lib/format"
import type { Batch, Movement, Product } from "@/types/api"

export function ProductDetail({ id }: { id: number }) {
  const { can } = useAuth()
  const { data: product, isLoading, error } = useQuery({ queryKey: ["products", "detail", id], queryFn: () => api.get<Product>(`/products/${id}`) })
  if (isLoading) return <PageLoading />
  if (error || !product) return <p className="mt-10 text-center text-sm text-muted-foreground" role="alert">{error instanceof ApiError && error.status === 404 ? "This product does not exist or was deleted." : errorMessage(error)}</p>
  return (
    <>
      <PageHeader
        back={{ href: "/products", label: "Products" }}
        title={product.name}
        description={<span className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs">{product.sku}</span><StatusBadge status={product.is_active ? "ACTIVE" : "INACTIVE"} /></span>}
      />
      <Tabs defaultValue="details">
        <TabsList className="mb-4">
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="stock">Stock & batches</TabsTrigger>
          <TabsTrigger value="barcodes">Barcodes</TabsTrigger>
          <TabsTrigger value="movements">Movements</TabsTrigger>
        </TabsList>
        <TabsContent value="details">
          <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
            {can("product.update") ? <ProductForm product={product} /> : <SectionCard title="Product"><p className="text-sm text-muted-foreground">You have read-only access to products.</p></SectionCard>}
            <div className="space-y-4">
              <ImageCard product={product} canEdit={can("product.update")} />
              <SectionCard title="At a glance">
                <dl className="divide-y">
                  <KeyValue label="In stock">{formatNumber(product.current_stock)} {product.unit.short_name}</KeyValue>
                  <KeyValue label="Selling price"><Money value={product.selling_price} /></KeyValue>
                  {product.purchase_price !== null && <KeyValue label="Cost"><Money value={product.purchase_price} /></KeyValue>}
                  {product.purchase_price !== null && product.selling_price > 0 && <KeyValue label="Margin">{(((product.selling_price - product.purchase_price) / product.selling_price) * 100).toFixed(1)}%</KeyValue>}
                  <KeyValue label="Reorder level">{formatNumber(product.reorder_level)}</KeyValue>
                </dl>
              </SectionCard>
            </div>
          </div>
        </TabsContent>
        <TabsContent value="stock"><BatchesTab productId={id} /></TabsContent>
        <TabsContent value="barcodes"><BarcodesTab product={product} /></TabsContent>
        <TabsContent value="movements"><MovementsTab productId={id} /></TabsContent>
      </Tabs>
    </>
  )
}

function ImageCard({ product, canEdit }: { product: Product; canEdit: boolean }) {
  const ref = useRef<HTMLInputElement>(null)
  const upload = useApiMutation(
    (file: File) => { const f = new FormData(); f.append("file", file); return api.upload<Product>(`/products/${product.id}/image`, f) },
    { success: "Image updated", invalidate: [["products"]] },
  )
  return (
    <SectionCard title="Image">
      <div className="flex aspect-square w-full items-center justify-center overflow-hidden rounded-lg border bg-muted">
        {product.image_path ? <Image src={mediaUrl(product.image_path)!} alt={product.name} width={300} height={300} className="size-full object-cover" unoptimized /> : <span className="text-3xl font-semibold text-muted-foreground/60">{product.name.slice(0, 2).toUpperCase()}</span>}
      </div>
      {canEdit && (
        <>
          <input ref={ref} type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="sr-only" aria-label="Upload product image"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) { if (f.size > 5 * 1024 * 1024) toast.error("Image must be smaller than 5 MB"); else upload.mutate(f) } e.target.value = "" }} />
          <Button variant="outline" className="mt-3 w-full" onClick={() => ref.current?.click()} disabled={upload.isPending}><Camera className="size-4" /> {product.image_path ? "Replace image" : "Upload image"}</Button>
        </>
      )}
    </SectionCard>
  )
}

function BatchesTab({ productId }: { productId: number }) {
  const { can } = useAuth()
  const { query, data, setPage } = useTableQuery<Batch>(`batches-${productId}`, "/inventory/batches", { filters: { product_id: productId }, enabled: can("inventory.read") })
  if (!can("inventory.read")) return <p className="text-sm text-muted-foreground">You don’t have access to inventory details.</p>
  return (
    <DataTable<Batch>
      page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(b) => b.id}
      empty={{ title: "No stock on hand", description: "Receive a purchase order or add a stock adjustment to create the first batch." }}
      columns={[
        { id: "batch", header: "Batch", cell: (b) => <span className="font-mono text-xs">{b.batch_number}</span> },
        { id: "expiry", header: "Expiry", cell: (b) => b.expiry_date ? <span className={b.days_to_expiry !== null && b.days_to_expiry < 0 ? "text-destructive" : ""}>{formatDate(b.expiry_date)}{b.days_to_expiry !== null && <span className="ml-1 text-xs text-muted-foreground">({b.days_to_expiry}d)</span>}</span> : "—" },
        { id: "received", header: "Received", align: "right", cell: (b) => formatNumber(b.quantity_received), hideOnMobile: true },
        { id: "remaining", header: "Remaining", align: "right", cell: (b) => <span className="font-medium tabular">{formatNumber(b.quantity_remaining)}</span> },
        ...(can("product.cost") ? [{ id: "cost", header: "Unit cost", align: "right" as const, cell: (b: Batch) => <Money value={b.purchase_cost} /> }, { id: "value", header: "Value", align: "right" as const, cell: (b: Batch) => <Money value={b.stock_value} /> }] : []),
        { id: "date", header: "Received on", cell: (b) => formatDate(b.received_at), hideOnMobile: true },
      ]}
    />
  )
}

function MovementsTab({ productId }: { productId: number }) {
  const { can } = useAuth()
  const { query, data, setPage } = useTableQuery<Movement>(`movements-${productId}`, "/inventory/movements", { filters: { product_id: productId }, enabled: can("inventory.read") })
  if (!can("inventory.read")) return <p className="text-sm text-muted-foreground">You don’t have access to inventory details.</p>
  return (
    <DataTable<Movement>
      page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(m) => m.id}
      empty={{ title: "No stock movements yet" }}
      columns={[
        { id: "date", header: "Date", cell: (m) => formatDateTime(m.created_at) },
        { id: "type", header: "Type", cell: (m) => <StatusBadge status={m.txn_type} tone={m.quantity > 0 ? "success" : "neutral"} /> },
        { id: "qty", header: "Qty", align: "right", cell: (m) => <span className={m.quantity > 0 ? "text-success tabular" : "tabular"}>{m.quantity > 0 ? "+" : ""}{formatNumber(m.quantity)}</span> },
        { id: "bal", header: "Balance", align: "right", cell: (m) => <span className="tabular">{formatNumber(m.balance_after)}</span> },
        { id: "reason", header: "Reason", cell: (m) => <span className="text-muted-foreground">{m.reason ?? "—"}</span>, hideOnMobile: true },
        { id: "user", header: "By", cell: (m) => m.user_name ?? "—", hideOnMobile: true },
      ]}
    />
  )
}

function BarcodesTab({ product }: { product: Product }) {
  const { can } = useAuth()
  const [code, setCode] = useState("")
  const add = useApiMutation((body: { barcode: string; is_primary: boolean }) => api.post(`/products/${product.id}/barcodes`, body), {
    success: "Barcode added", invalidate: [["products"]], onSuccess: () => setCode(""),
  })
  const remove = useApiMutation((bid: number) => api.delete(`/products/${product.id}/barcodes/${bid}`), { success: "Barcode removed", invalidate: [["products"]] })
  return (
    <SectionCard title="Barcodes" description="A product can carry several barcodes (e.g. different pack sizes). Each must be unique across the shop.">
      <ul className="divide-y rounded-lg border">
        {product.barcodes.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted-foreground">No barcodes assigned yet.</li>}
        {product.barcodes.map((b) => (
          <li key={b.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
            <span className="font-mono text-sm">{b.barcode}</span>
            <span className="flex items-center gap-2">
              {b.is_primary && <StatusBadge status="ACTIVE" label="Primary" />}
              {can("product.update") && <Button variant="ghost" size="icon-sm" aria-label={`Remove barcode ${b.barcode}`} onClick={() => remove.mutate(b.id)}><Trash2 className="size-4 text-muted-foreground" /></Button>}
            </span>
          </li>
        ))}
      </ul>
      {can("product.update") && (
        <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (code.trim()) add.mutate({ barcode: code.trim(), is_primary: product.barcodes.length === 0 }) }}>
          <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Scan or type a barcode" aria-label="New barcode" className="max-w-xs font-mono" />
          <Button type="submit" disabled={!code.trim() || add.isPending}><Plus className="size-4" /> Add</Button>
        </form>
      )}
    </SectionCard>
  )
}
