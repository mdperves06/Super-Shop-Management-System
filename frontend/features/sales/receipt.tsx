"use client"

import { mediaUrl } from "@/lib/api"
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format"
import { useShopSettings } from "@/lib/settings"
import type { Sale } from "@/types/api"

const m = (v: number) => formatMoney(v, { symbol: false })

/** Thermal-printer friendly receipt (80 mm). Numbers come from the server-created sale record. */
export function Receipt({ sale }: { sale: Sale }) {
  const s = useShopSettings()
  const width = Number(s["receipt.paper_width_mm"] ?? 80)
  const logo = s["shop.logo"] ? mediaUrl(String(s["shop.logo"])) : null
  const includeTax = s["tax.prices_include_tax"] !== false
  return (
    <div className="receipt-paper mx-auto bg-white p-3 font-mono text-[11px] leading-snug text-black" style={{ width: `${width}mm`, maxWidth: "100%" }}>
      <div className="text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {logo && <img src={logo} alt="" className="mx-auto mb-1 max-h-12" />}
        <p className="text-sm font-bold">{String(s["shop.name"] ?? "")}</p>
        <p>{String(s["shop.address"] ?? "")}</p>
        <p>Tel: {String(s["shop.phone"] ?? "")}</p>
        {s["shop.bin"] ? <p>BIN: {String(s["shop.bin"])}</p> : null}
        {s["receipt.header"] ? <p>{String(s["receipt.header"])}</p> : null}
      </div>
      <hr className="my-1.5 border-dashed border-black" />
      <p className="font-bold">Invoice: {sale.invoice_number}</p>
      <p>Date: {formatDateTime(sale.sale_date)}</p>
      <p>Cashier: {sale.cashier_name}</p>
      {sale.customer_name && <p>Customer: {sale.customer_name}{sale.customer_phone ? ` (${sale.customer_phone})` : ""}</p>}
      {sale.status === "VOIDED" && <p className="my-1 text-center text-sm font-bold">*** VOIDED ***</p>}
      <hr className="my-1.5 border-dashed border-black" />
      {sale.items.map((i) => (
        <div key={i.id} className="mb-1">
          <p className="font-semibold">{i.product_name}</p>
          <div className="flex justify-between"><span>{formatNumber(i.quantity)} × {m(i.unit_price)}</span><span>{m(i.line_total + i.discount_amount)}</span></div>
          {i.discount_amount > 0 && <div className="flex justify-between"><span>  Discount</span><span>-{m(i.discount_amount)}</span></div>}
        </div>
      ))}
      <hr className="my-1.5 border-dashed border-black" />
      <div className="flex justify-between"><span>Subtotal</span><span>{m(sale.subtotal)}</span></div>
      {sale.discount_amount > 0 && <div className="flex justify-between"><span>Discount</span><span>-{m(sale.discount_amount)}</span></div>}
      {s["receipt.show_tax"] !== false && sale.tax_amount > 0 && <div className="flex justify-between"><span>{includeTax ? "VAT (incl.)" : "VAT"}</span><span>{m(sale.tax_amount)}</span></div>}
      <div className="mt-1 flex justify-between text-sm font-bold"><span>TOTAL</span><span>{formatMoney(sale.total_amount)}</span></div>
      <hr className="my-1.5 border-dashed border-black" />
      {sale.payments.map((p) => (
        <div key={p.id} className="flex justify-between"><span>{p.method_name}{p.transaction_id ? ` (${p.transaction_id})` : ""}</span><span>{m(p.amount)}</span></div>
      ))}
      {sale.change_amount > 0 && <div className="flex justify-between font-bold"><span>Change</span><span>{m(sale.change_amount)}</span></div>}
      {sale.due_amount > 0 && <div className="flex justify-between font-bold"><span>DUE (credit)</span><span>{formatMoney(sale.due_amount)}</span></div>}
      <hr className="my-1.5 border-dashed border-black" />
      <p className="text-center">{String(s["receipt.footer"] ?? "Thank you!")}</p>
    </div>
  )
}

/** A4 tax invoice for printing from the browser. */
export function A4Invoice({ sale }: { sale: Sale }) {
  const s = useShopSettings()
  const logo = s["shop.logo"] ? mediaUrl(String(s["shop.logo"])) : null
  return (
    <div className="mx-auto w-[190mm] max-w-full bg-white p-6 text-[12px] text-black">
      <div className="flex items-start justify-between">
        <div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {logo && <img src={logo} alt="" className="mb-2 max-h-14" />}
          <p className="text-lg font-bold">{String(s["shop.name"] ?? "")}</p>
          <p>{String(s["shop.address"] ?? "")}</p>
          <p>Tel {String(s["shop.phone"] ?? "")} {s["shop.email"] ? `· ${String(s["shop.email"])}` : ""}</p>
          {s["shop.bin"] ? <p>BIN {String(s["shop.bin"])}</p> : null}
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold tracking-wide">INVOICE</p>
          <p className="font-mono">{sale.invoice_number}</p>
          <p>{formatDateTime(sale.sale_date)}</p>
          {sale.status === "VOIDED" && <p className="mt-1 text-lg font-bold">VOIDED</p>}
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 border-y py-2">
        <div><p className="text-[10px] tracking-wide uppercase opacity-70">Billed to</p><p className="font-semibold">{sale.customer_name ?? "Walk-in customer"}</p>{sale.customer_phone && <p>{sale.customer_phone}</p>}</div>
        <div><p className="text-[10px] tracking-wide uppercase opacity-70">Served by</p><p className="font-semibold">{sale.cashier_name}</p></div>
      </div>
      <table className="mt-3 w-full border-collapse">
        <thead><tr className="border-b-2 text-left"><th className="py-1">#</th><th>Item</th><th className="text-right">Qty</th><th className="text-right">Price</th><th className="text-right">Discount</th><th className="text-right">VAT</th><th className="text-right">Total</th></tr></thead>
        <tbody>
          {sale.items.map((i, n) => (
            <tr key={i.id} className="border-b"><td className="py-1">{n + 1}</td><td>{i.product_name}<span className="block font-mono text-[10px] opacity-70">{i.sku}</span></td>
              <td className="text-right">{formatNumber(i.quantity)}</td><td className="text-right">{m(i.unit_price)}</td><td className="text-right">{m(i.discount_amount)}</td><td className="text-right">{m(i.tax_amount)}</td><td className="text-right font-semibold">{m(i.line_total)}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 ml-auto w-64 space-y-0.5">
        <div className="flex justify-between"><span>Subtotal</span><span>{formatMoney(sale.subtotal)}</span></div>
        <div className="flex justify-between"><span>Discount</span><span>-{formatMoney(sale.discount_amount)}</span></div>
        <div className="flex justify-between"><span>VAT</span><span>{formatMoney(sale.tax_amount)}</span></div>
        <div className="flex justify-between border-t pt-1 text-base font-bold"><span>Total</span><span>{formatMoney(sale.total_amount)}</span></div>
        <div className="flex justify-between"><span>Paid</span><span>{formatMoney(sale.paid_amount)}</span></div>
        {sale.due_amount > 0 && <div className="flex justify-between font-bold"><span>Balance due</span><span>{formatMoney(sale.due_amount)}</span></div>}
      </div>
      <p className="mt-2 text-[11px]">Payment: {sale.payments.map((p) => `${p.method_name} ${formatMoney(p.amount)}`).join(", ") || "—"}</p>
      <p className="mt-8 text-center text-[11px] opacity-80">{String(s["receipt.footer"] ?? "")}</p>
    </div>
  )
}
