"use client"

import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, FileText, Minus, Percent, Plus, Printer, ScanBarcode, Search, ShoppingCart, Trash2, UserPlus, X } from "lucide-react"
import Image from "next/image"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

import { AsyncCombobox, type Option } from "@/components/shared/combobox"
import { PrintPortal, printPage } from "@/components/shared/print"
import { Money, NativeSelect, PageLoading } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { CustomerDialog } from "@/features/parties/customers"
import { PaymentDialog } from "@/features/pos/payment-dialog"
import { OpenRegisterCard, useCurrentSession } from "@/features/pos/register-gate"
import { useCart, type CartLine } from "@/features/pos/use-cart"
import { Receipt } from "@/features/sales/receipt"
import { useDebounce } from "@/hooks/use-debounce"
import { api, mediaUrl, openFile } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatMoney, formatNumber } from "@/lib/format"
import { useT } from "@/lib/i18n"
import { cn } from "@/lib/utils"
import { searchCustomers, useCategories } from "@/services/lookups"
import type { CartPreview, Customer, ProductLookup, Sale } from "@/types/api"

export function PosScreen() {
  const session = useCurrentSession()
  if (session.isLoading) return <PageLoading />
  if (!session.data) return <OpenRegisterCard />
  return <PosTerminal registerName={session.data.register_name} />
}

function PosTerminal({ registerName }: { registerName: string }) {
  const t = useT()
  const { can } = useAuth()
  const [customer, setCustomer] = useState<Option | null>(null)
  const [customerFull, setCustomerFull] = useState<Customer | null>(null)
  const cart = useCart(customer?.id ?? null)
  const [query, setQuery] = useState("")
  const [category, setCategory] = useState<number | null>(null)
  const [view, setView] = useState<"products" | "cart">("products")
  const [payOpen, setPayOpen] = useState(false)
  const [completed, setCompleted] = useState<Sale | null>(null)
  const [printing, setPrinting] = useState<Sale | null>(null)
  const [newCustomer, setNewCustomer] = useState(false)
  const [flash, setFlash] = useState<number | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const debounced = useDebounce(query.trim(), 220)
  const cats = useCategories()

  const products = useQuery({
    queryKey: ["pos-products", debounced, category],
    queryFn: () => api.get<ProductLookup[]>("/products/lookup", { q: debounced, category_id: category ?? undefined, limit: 60 }),
    staleTime: 15_000,
  })

  // keep the barcode field ready: a USB scanner types like a keyboard, so stray keystrokes go to the search box
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      const typing = el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable
      if (e.key === "F2") { e.preventDefault(); searchRef.current?.focus(); searchRef.current?.select() }
      else if (e.key === "F9") { e.preventDefault(); if (cart.valid && cart.preview.data) setPayOpen(true) }
      else if (!typing && !payOpen && !completed && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) searchRef.current?.focus()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [cart.valid, cart.preview.data, payOpen, completed])

  const addProduct = useCallback((p: ProductLookup) => {
    if (p.current_stock <= 0) { toast.warning(`${p.name} is out of stock`); return }
    cart.add(p, 1)
    setFlash(p.id)
    setTimeout(() => setFlash((f) => (f === p.id ? null : f)), 700)
  }, [cart])

  async function onEnter() {
    const code = query.trim()
    if (!code) return
    setQuery("") // clear at once so the next scan (a scanner can fire every ~100 ms) starts from an empty field
    try {
      const found = await api.get<ProductLookup[]>("/products/lookup", { q: code, limit: 5 })
      const exact = found.find((p) => p.barcode === code || p.sku.toLowerCase() === code.toLowerCase())
      if (exact || found.length === 1) addProduct(exact ?? found[0])
      else if (found.length === 0) toast.error(`No product found for “${code}”`)
      else setQuery(code) // ambiguous text search: show the matches for the cashier to pick
    } catch (e) { toast.error((e as Error).message) }
  }

  function newSale() {
    cart.clear()
    setCompleted(null)
    setCustomer(null)
    setCustomerFull(null)
    setView("products")
    setQuery("")
    setTimeout(() => searchRef.current?.focus(), 50)
  }

  function print(sale: Sale) {
    setPrinting(sale)
    printPage("size: 80mm auto; margin: 2mm")
  }

  const p = cart.preview.data
  const lineTotals = useMemo(() => new Map((p?.lines ?? []).map((l) => [l.product_id, l])), [p])
  const busy = cart.preview.isFetching
  const errorMsg = cart.preview.error ? (cart.preview.error as Error).message : null

  return (
    <div className="flex h-[calc(100vh-6.5rem)] min-h-[560px] flex-col gap-3">
      {/* mobile switch */}
      <div className="grid grid-cols-2 gap-1 rounded-xl bg-muted p-1 lg:hidden" role="tablist" aria-label="POS view">
        {(["products", "cart"] as const).map((v) => (
          <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)} className={cn("h-11 rounded-lg text-sm font-medium", view === v ? "bg-background shadow-sm" : "text-muted-foreground")}>
            {v === "products" ? "Products" : `Cart (${cart.lines.length})`}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_420px] xl:grid-cols-[minmax(0,1fr)_460px]">
        {/* ---------- products ---------- */}
        <section className={cn("flex min-h-0 min-w-0 flex-col gap-3", view === "cart" && "hidden lg:flex")} aria-label="Products">
          <div className="relative">
            <ScanBarcode className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input ref={searchRef} autoFocus value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void onEnter() } }}
              placeholder={t("pos.scan")} aria-label="Scan barcode or search product" autoComplete="off" className="h-12 pr-24 pl-11 text-base" />
            <span className="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 text-[11px] text-muted-foreground sm:block">F2 focus · Enter add</span>
          </div>
          <div className="scroll-thin -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="group" aria-label="Categories">
            <Chip active={category === null} onClick={() => setCategory(null)}>{t("common.all")}</Chip>
            {cats.data?.filter((c) => c.parent_id === null).map((c) => <Chip key={c.id} active={category === c.id} onClick={() => setCategory(c.id)}>{c.name}</Chip>)}
          </div>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto pr-1">
            {products.isLoading ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">{Array.from({ length: 12 }).map((_, i) => <div key={i} className="h-28 animate-pulse rounded-xl bg-muted" />)}</div>
            ) : (products.data?.length ?? 0) === 0 ? (
              <div className="flex h-48 flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground"><Search className="size-6" />No products match “{debounced}”.</div>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
                {products.data!.map((pr) => {
                  const out = pr.current_stock <= 0
                  return (
                    <button key={pr.id} type="button" disabled={out} onClick={() => addProduct(pr)} aria-label={`Add ${pr.name}, ${formatMoney(pr.selling_price)}${out ? ", out of stock" : ""}`}
                      className={cn("group flex min-h-28 flex-col justify-between rounded-xl border bg-card p-3 text-left transition hover:border-primary hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]", out && "cursor-not-allowed opacity-50")}>
                      <div className="flex items-start gap-2">
                        {pr.image_path && <Image src={mediaUrl(pr.image_path)!} alt="" width={36} height={36} className="size-9 shrink-0 rounded object-cover" unoptimized />}
                        <span className="line-clamp-2 text-sm leading-tight font-medium">{pr.name}</span>
                      </div>
                      <div className="mt-2 flex items-end justify-between">
                        <span className="text-base font-bold tabular">{formatMoney(pr.selling_price)}</span>
                        <span className={cn("text-xs tabular", out ? "text-destructive" : pr.current_stock <= 5 ? "text-warning" : "text-muted-foreground")}>{out ? "Out" : `${formatNumber(pr.current_stock)} ${pr.unit}`}</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </section>

        {/* ---------- cart ---------- */}
        <section className={cn("flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border bg-card", view === "products" && "hidden lg:flex")} aria-label={t("pos.cart")}>
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div><h2 className="font-semibold">{t("pos.cart")}</h2><p className="text-xs text-muted-foreground">{registerName}</p></div>
            {cart.lines.length > 0 && <Button variant="ghost" size="sm" onClick={cart.clear}><Trash2 className="size-4" /> {t("pos.clear")}</Button>}
          </div>

          <div className="flex items-center gap-2 border-b px-4 py-2.5">
            <div className="min-w-0 flex-1">
              <AsyncCombobox value={customer} onChange={(o) => { setCustomer(o); if (!o) setCustomerFull(null); else void api.get<Customer>(`/customers/${o.id}`).then(setCustomerFull).catch(() => setCustomerFull(null)) }}
                fetcher={searchCustomers} queryKey="customers" placeholder={t("pos.walkin")} />
            </div>
            {can("customer.create") && <Button variant="outline" size="icon" aria-label="Add new customer" onClick={() => setNewCustomer(true)}><UserPlus className="size-4" /></Button>}
          </div>
          {customerFull && (customerFull.balance > 0 || customerFull.discount_percent > 0) && (
            <p className="border-b bg-muted/40 px-4 py-1.5 text-xs text-muted-foreground">
              {customerFull.balance > 0 && <>Owes {formatMoney(customerFull.balance)}. </>}{customerFull.discount_percent > 0 && <>Standing discount {customerFull.discount_percent}%.</>}
            </p>
          )}

          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
            {cart.lines.length === 0 ? (
              <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 px-6 text-center text-sm text-muted-foreground"><ShoppingCart className="size-8 opacity-50" />{t("pos.empty")}</div>
            ) : (
              <ul className="divide-y">
                {cart.lines.map((l) => (
                  <CartRow key={l.product.id} line={l} calc={lineTotals.get(l.product.id)} flash={flash === l.product.id}
                    onQty={(q) => cart.setQuantity(l.product.id, q)} onRemove={() => cart.remove(l.product.id)}
                    onDiscount={(type, value) => cart.setLineDiscount(l.product.id, type, value)} />
                ))}
              </ul>
            )}
          </div>

          <Totals preview={p} busy={busy} error={errorMsg} invoiceDiscount={cart.invoiceDiscount} onInvoiceDiscount={cart.setInvoiceDiscount} disabled={cart.lines.length === 0} />

          <div className="border-t p-3">
            <Button size="xl" className="w-full" disabled={!p || !cart.valid || !!errorMsg || busy || !p.discount_allowed} onClick={() => setPayOpen(true)}>
              {t("pos.pay")} {p ? formatMoney(p.grand_total) : ""} <kbd className="ml-2 hidden rounded bg-primary-foreground/20 px-1.5 text-xs sm:inline">F9</kbd>
            </Button>
          </div>
        </section>
      </div>

      {/* mobile sticky total */}
      {view === "products" && cart.lines.length > 0 && (
        <button className="fixed inset-x-3 bottom-3 z-20 flex h-14 items-center justify-between rounded-xl bg-primary px-5 text-primary-foreground shadow-lg lg:hidden" onClick={() => setView("cart")}>
          <span className="flex items-center gap-2"><ShoppingCart className="size-5" /> {cart.lines.length} item(s)</span><span className="text-lg font-bold tabular">{p ? formatMoney(p.grand_total) : "…"}</span>
        </button>
      )}

      {p && (
        <PaymentDialog open={payOpen} onClose={() => setPayOpen(false)} total={p.grand_total} payload={cart.payload} customerName={customer?.label ?? null}
          hasCustomer={!!customer} creditAvailable={p.credit_available}
          onDone={(sale) => { setPayOpen(false); setCompleted(sale); toast.success(t("pos.completed")); void products.refetch() }} />
      )}

      <Dialog open={!!completed} onOpenChange={() => { /* must choose an action */ }}>
        <DialogContent className="sm:max-w-md" showCloseButton={false}>
          {completed && (
            <>
              <DialogHeader className="items-center text-center">
                <span className="mb-1 flex size-14 items-center justify-center rounded-full bg-success/15 text-success"><CheckCircle2 className="size-8" /></span>
                <DialogTitle className="text-lg">{t("pos.completed")}</DialogTitle>
                <DialogDescription>{completed.invoice_number}</DialogDescription>
              </DialogHeader>
              <dl className="space-y-1 rounded-xl bg-muted/60 p-4 text-sm">
                <div className="flex justify-between"><dt>Total</dt><dd className="font-semibold tabular">{formatMoney(completed.total_amount)}</dd></div>
                <div className="flex justify-between"><dt>Paid</dt><dd className="tabular">{formatMoney(completed.paid_amount)}</dd></div>
                {completed.change_amount > 0 && <div className="flex justify-between text-lg font-bold text-success"><dt>{t("pos.change")}</dt><dd className="tabular">{formatMoney(completed.change_amount)}</dd></div>}
                {completed.due_amount > 0 && <div className="flex justify-between font-semibold text-destructive"><dt>{t("pos.due")}</dt><dd className="tabular">{formatMoney(completed.due_amount)}</dd></div>}
              </dl>
              <div className="grid gap-2 sm:grid-cols-2">
                <Button size="lg" variant="outline" onClick={() => print(completed)}><Printer className="size-4" /> {t("pos.printReceipt")}</Button>
                <Button size="lg" variant="outline" onClick={() => void openFile(`/documents/sales/${completed.id}/receipt.pdf`)}><FileText className="size-4" /> {t("pos.downloadPdf")}</Button>
              </div>
              <Button size="xl" autoFocus onClick={newSale}>{t("pos.newSale")}</Button>
            </>
          )}
        </DialogContent>
      </Dialog>

      {printing && <PrintPortal><Receipt sale={printing} /></PrintPortal>}
      <CustomerDialog customer={newCustomer ? "new" : null} onClose={() => setNewCustomer(false)} onSaved={(c) => { setCustomer({ id: c.id, label: c.name, hint: c.phone ?? c.code }); setCustomerFull(c) }} />
    </div>
  )
}

function Chip({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active} className={cn("h-9 shrink-0 rounded-full border px-4 text-sm font-medium whitespace-nowrap transition", active ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-muted")}>
      {children}
    </button>
  )
}

function CartRow({ line, calc, flash, onQty, onRemove, onDiscount }: {
  line: CartLine
  calc?: CartPreview["lines"][number]
  flash: boolean
  onQty: (q: number) => void
  onRemove: () => void
  onDiscount: (type: "PERCENT" | "FIXED" | undefined, value: number) => void
}) {
  const [open, setOpen] = useState(false)
  const step = line.product.allow_decimal ? 0.5 : 1
  const overStock = calc ? line.quantity > calc.stock_available : false
  return (
    <li className={cn("px-4 py-3 transition-colors", flash && "bg-primary/10")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{line.product.name}</p>
          <p className="text-xs text-muted-foreground tabular">{formatMoney(line.product.selling_price)} / {line.product.unit}</p>
        </div>
        <div className="text-right">
          <Money value={calc?.line_total} className="text-sm font-semibold" />
          {calc && calc.discount > 0 && <p className="text-[11px] text-success tabular">−{formatMoney(calc.discount)}{calc.promotion ? ` · ${calc.promotion}` : ""}</p>}
        </div>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="flex items-center rounded-lg border">
          <Button variant="ghost" size="icon" className="size-10" aria-label={`Decrease ${line.product.name}`} onClick={() => (line.quantity - step <= 0 ? onRemove() : onQty(Math.round((line.quantity - step) * 1000) / 1000))}><Minus className="size-4" /></Button>
          <Input type="number" min="0" step={line.product.allow_decimal ? "0.1" : "1"} value={line.quantity} aria-label={`Quantity of ${line.product.name}`} className="h-10 w-16 border-0 px-0 text-center text-base font-semibold tabular focus-visible:ring-0"
            onChange={(e) => { const v = Number(e.target.value); if (!Number.isNaN(v)) onQty(v) }} />
          <Button variant="ghost" size="icon" className="size-10" aria-label={`Increase ${line.product.name}`} onClick={() => onQty(Math.round((line.quantity + step) * 1000) / 1000)}><Plus className="size-4" /></Button>
        </div>
        <Button variant={line.discountValue > 0 ? "secondary" : "ghost"} size="sm" className="h-10" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={`Discount for ${line.product.name}`}>
          <Percent className="size-4" />{line.discountValue > 0 && <span className="tabular">{line.discountType === "PERCENT" ? `${line.discountValue}%` : formatMoney(line.discountValue)}</span>}
        </Button>
        <Button variant="ghost" size="icon" className="ml-auto size-10" aria-label={`Remove ${line.product.name}`} onClick={onRemove}><X className="size-4" /></Button>
      </div>
      {overStock && <p className="mt-1.5 flex items-center gap-1 text-xs text-warning" role="status"><AlertTriangle className="size-3.5" />Only {formatNumber(calc!.stock_available)} in stock</p>}
      {open && (
        <div className="mt-2 flex items-center gap-2 rounded-lg bg-muted/60 p-2">
          <NativeSelect aria-label="Discount type" className="w-24" value={line.discountType ?? "PERCENT"} onChange={(e) => onDiscount(e.target.value as "PERCENT" | "FIXED", line.discountValue)}><option value="PERCENT">%</option><option value="FIXED">৳</option></NativeSelect>
          <Input type="number" min="0" step="0.01" aria-label="Discount value" placeholder="0" value={line.discountValue || ""} onChange={(e) => onDiscount(line.discountType ?? "PERCENT", Number(e.target.value) || 0)} className="tabular" />
          <Button variant="ghost" size="sm" onClick={() => { onDiscount(undefined, 0); setOpen(false) }}>Clear</Button>
        </div>
      )}
    </li>
  )
}

function Totals({ preview, busy, error, invoiceDiscount, onInvoiceDiscount, disabled }: {
  preview?: CartPreview
  busy: boolean
  error: string | null
  invoiceDiscount: { type: "PERCENT" | "FIXED"; value: number } | null
  onInvoiceDiscount: (d: { type: "PERCENT" | "FIXED"; value: number } | null) => void
  disabled: boolean
}) {
  const t = useT()
  return (
    <div className={cn("space-y-1.5 border-t bg-muted/30 px-4 py-3 text-sm", busy && "opacity-80")}>
      {error && <p className="flex items-start gap-1.5 rounded-md bg-destructive/10 px-2 py-1.5 text-xs text-destructive" role="alert"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{error}</p>}
      <div className="flex items-center gap-2">
        <label htmlFor="inv-disc" className="shrink-0 text-muted-foreground">Invoice discount</label>
        <NativeSelect aria-label="Invoice discount type" className="ml-auto h-8 w-16 text-xs" disabled={disabled} value={invoiceDiscount?.type ?? "PERCENT"} onChange={(e) => onInvoiceDiscount({ type: e.target.value as "PERCENT" | "FIXED", value: invoiceDiscount?.value ?? 0 })}><option value="PERCENT">%</option><option value="FIXED">৳</option></NativeSelect>
        <Input id="inv-disc" type="number" min="0" step="0.01" disabled={disabled} value={invoiceDiscount?.value || ""} placeholder="0" onChange={(e) => onInvoiceDiscount({ type: invoiceDiscount?.type ?? "PERCENT", value: Number(e.target.value) || 0 })} className="h-8 w-24 text-right tabular" />
      </div>
      {preview && !preview.discount_allowed && (
        <p className="rounded-md bg-warning/15 px-2 py-1.5 text-xs text-[oklch(0.45_0.12_70)] dark:text-warning" role="alert">
          Discount {preview.manual_discount_percent}% is above your limit of {preview.max_discount_percent}%. Reduce it or ask a manager to process this sale.
        </p>
      )}
      <Row label={t("pos.subtotal")} value={preview?.subtotal} />
      <Row label={t("pos.discount")} value={preview ? -preview.discount_total : undefined} accent={!!preview?.discount_total} />
      <Row label={t("pos.tax")} value={preview?.tax_total} muted />
      <div className="flex items-baseline justify-between border-t pt-2"><span className="text-base font-semibold">{t("pos.total")}</span><Money value={preview?.grand_total} className="text-2xl font-bold" /></div>
    </div>
  )
}

function Row({ label, value, accent, muted }: { label: string; value?: number; accent?: boolean; muted?: boolean }) {
  return <div className={cn("flex justify-between", muted && "text-muted-foreground", accent && "text-success")}><span>{label}</span><span className="tabular">{value === undefined ? "—" : formatMoney(value)}</span></div>
}
