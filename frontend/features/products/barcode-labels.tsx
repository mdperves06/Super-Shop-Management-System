"use client"

import JsBarcode from "jsbarcode"
import { Plus, Printer, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { AsyncCombobox } from "@/components/shared/combobox"
import { Field, NativeSelect, PageHeader, SectionCard } from "@/components/shared/ui-parts"
import { PrintPortal, printPage } from "@/components/shared/print"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"
import { formatMoney } from "@/lib/format"
import { searchProducts } from "@/services/lookups"
import type { Page, Product } from "@/types/api"

const FORMATS = ["CODE128", "EAN13", "EAN8", "UPC", "CODE39", "ITF14"] as const
type BarcodeFormat = (typeof FORMATS)[number]

interface LabelItem { product: Product; copies: number }

function BarcodeSvg({ value, format, height = 40 }: { value: string; format: BarcodeFormat; height?: number }) {
  const ref = useRef<SVGSVGElement>(null)
  const [invalid, setInvalid] = useState(false)
  useEffect(() => {
    if (!ref.current) return
    try {
      JsBarcode(ref.current, value, { format, height, width: 1.6, fontSize: 12, margin: 0, displayValue: true, background: "transparent", lineColor: "#000" })
      setInvalid(false) // eslint-disable-line react-hooks/set-state-in-effect
    } catch {
      setInvalid(true)
    }
  }, [value, format, height])
  if (invalid) return <div className="rounded border border-dashed p-2 text-center text-[10px] text-destructive">“{value}” is not valid for {format}</div>
  return <svg ref={ref} className="max-w-full" aria-label={`Barcode ${value}`} role="img" />
}

export function BarcodeLabelsPage() {
  const [items, setItems] = useState<LabelItem[]>([])
  const [format, setFormat] = useState<BarcodeFormat>("CODE128")
  const [showPrice, setShowPrice] = useState(true)
  const [cols, setCols] = useState(3)

  async function add(id: number) {
    if (items.some((i) => i.product.id === id)) return
    const p = await api.get<Product>(`/products/${id}`)
    setItems((prev) => [...prev, { product: p, copies: 1 }])
  }

  const labels = items.flatMap((i) => Array.from({ length: i.copies }, () => i.product)).filter((p) => p.barcode)
  const missing = items.filter((i) => !i.product.barcode)

  return (
    <>
      <PageHeader title="Barcode labels" description="Choose products, pick a barcode format and print shelf labels."
        actions={<Button onClick={() => printPage()} disabled={labels.length === 0}><Printer className="size-4" /> Print labels</Button>} />
      <div className="no-print grid gap-4 lg:grid-cols-[380px_1fr]">
        <SectionCard title="Labels to print">
          <div className="space-y-4">
            <Field label="Add product">{(p) => <AsyncCombobox id={p.id} value={null} onChange={(o) => o && void add(o.id)} fetcher={searchProducts} queryKey="products" placeholder="Search product…" clearable={false} />}</Field>
            <ul className="divide-y rounded-lg border" aria-label="Selected products">
              {items.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted-foreground">Add products to build a label sheet.</li>}
              {items.map((i) => (
                <li key={i.product.id} className="flex items-center gap-2 px-3 py-2">
                  <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{i.product.name}</p><p className="font-mono text-xs text-muted-foreground">{i.product.barcode ?? "no barcode"}</p></div>
                  <Input type="number" min={1} max={200} value={i.copies} aria-label={`Copies of ${i.product.name}`} className="w-16"
                    onChange={(e) => setItems((prev) => prev.map((x) => x.product.id === i.product.id ? { ...x, copies: Math.max(1, Math.min(200, Number(e.target.value) || 1)) } : x))} />
                  <Button variant="ghost" size="icon-sm" aria-label={`Remove ${i.product.name}`} onClick={() => setItems((prev) => prev.filter((x) => x.product.id !== i.product.id))}><X className="size-4" /></Button>
                </li>
              ))}
            </ul>
            {missing.length > 0 && <p className="text-xs text-warning" role="status">{missing.map((m) => m.product.name).join(", ")} have no barcode and will be skipped.</p>}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Format">{(p) => <NativeSelect {...p} value={format} onChange={(e) => setFormat(e.target.value as BarcodeFormat)}>{FORMATS.map((f) => <option key={f}>{f}</option>)}</NativeSelect>}</Field>
              <Field label="Labels per row">{(p) => <NativeSelect {...p} value={cols} onChange={(e) => setCols(Number(e.target.value))}>{[2, 3, 4, 5].map((c) => <option key={c}>{c}</option>)}</NativeSelect>}</Field>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showPrice} onChange={(e) => setShowPrice(e.target.checked)} className="size-4 accent-primary" /> Print price on label</label>
            <p className="text-xs text-muted-foreground">EAN-13 needs 12–13 digits, EAN-8 needs 7–8. Code 128 accepts any text and is the safest choice for internal codes.</p>
          </div>
        </SectionCard>

        <SectionCard title={`Preview (${labels.length} label${labels.length === 1 ? "" : "s"})`}>
          <LabelSheet labels={labels} format={format} showPrice={showPrice} cols={cols} />
        </SectionCard>
      </div>
      <PrintPortal><LabelSheet labels={labels} format={format} showPrice={showPrice} cols={cols} print /></PrintPortal>
    </>
  )
}

function LabelSheet({ labels, format, showPrice, cols, print }: { labels: Product[]; format: BarcodeFormat; showPrice: boolean; cols: number; print?: boolean }) {
  if (labels.length === 0 && !print) return <div className="flex h-48 items-center justify-center text-sm text-muted-foreground"><Plus className="mr-2 size-4" /> Nothing to preview yet</div>
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
      {labels.map((p, idx) => (
        <div key={`${p.id}-${idx}`} className="flex break-inside-avoid flex-col items-center rounded border border-dashed p-2 text-center" style={{ breakInside: "avoid" }}>
          <p className="w-full truncate text-[11px] font-semibold">{p.name}</p>
          <BarcodeSvg value={p.barcode!} format={format} />
          {showPrice && <p className="text-xs font-bold">{formatMoney(p.selling_price)}</p>}
        </div>
      ))}
    </div>
  )
}

// exported for tests
export type { Page }
