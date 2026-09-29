"use client"

import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { useCallback, useMemo, useState } from "react"

import { useDebounce } from "@/hooks/use-debounce"
import { api } from "@/lib/api"
import type { CartPreview, ProductLookup } from "@/types/api"

export interface CartLine {
  product: ProductLookup
  quantity: number
  discountType?: "PERCENT" | "FIXED"
  discountValue: number
}

export interface InvoiceDiscount {
  type: "PERCENT" | "FIXED"
  value: number
}

/**
 * POS cart state. Prices, discounts, VAT and totals are never computed here: every change is sent to
 * POST /sales/preview and the server's numbers are displayed.
 */
export function useCart(customerId: number | null) {
  const [lines, setLines] = useState<CartLine[]>([])
  const [invoiceDiscount, setInvoiceDiscount] = useState<InvoiceDiscount | null>(null)

  const add = useCallback((product: ProductLookup, qty = 1) => {
    setLines((prev) => {
      const i = prev.findIndex((l) => l.product.id === product.id)
      if (i >= 0) return prev.map((l, idx) => (idx === i ? { ...l, quantity: round(l.quantity + qty) } : l))
      return [...prev, { product, quantity: qty, discountValue: 0 }]
    })
  }, [])

  const setQuantity = useCallback((productId: number, quantity: number) => {
    setLines((prev) => prev.map((l) => (l.product.id === productId ? { ...l, quantity } : l)))
  }, [])

  const setLineDiscount = useCallback((productId: number, type: "PERCENT" | "FIXED" | undefined, value: number) => {
    setLines((prev) => prev.map((l) => (l.product.id === productId ? { ...l, discountType: value > 0 ? type : undefined, discountValue: value } : l)))
  }, [])

  const remove = useCallback((productId: number) => setLines((prev) => prev.filter((l) => l.product.id !== productId)), [])
  const clear = useCallback(() => { setLines([]); setInvoiceDiscount(null) }, [])

  const payload = useMemo(
    () => ({
      items: lines.map((l) => ({ product_id: l.product.id, quantity: l.quantity, discount_type: l.discountType, discount_value: l.discountValue || 0 })),
      customer_id: customerId,
      invoice_discount_type: invoiceDiscount?.value ? invoiceDiscount.type : undefined,
      invoice_discount_value: invoiceDiscount?.value || 0,
    }),
    [lines, customerId, invoiceDiscount],
  )
  const valid = lines.length > 0 && lines.every((l) => l.quantity > 0)
  const debounced = useDebounce(payload, 200)

  const preview = useQuery({
    queryKey: ["pos-preview", debounced],
    queryFn: () => api.post<CartPreview>("/sales/preview", debounced),
    enabled: valid && debounced.items.length > 0 && debounced.items.every((i) => i.quantity > 0),
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: 0,
  })

  return { lines, add, setQuantity, setLineDiscount, remove, clear, invoiceDiscount, setInvoiceDiscount, payload, preview, valid, count: lines.reduce((s, l) => s + (l.product.allow_decimal ? 1 : l.quantity), 0) }
}

const round = (n: number) => Math.round(n * 1000) / 1000
