"use client"

import { useQuery } from "@tanstack/react-query"

import type { Option } from "@/components/shared/combobox"
import { api } from "@/lib/api"
import type { Brand, Category, Customer, PaymentMethod, Page, Product, Supplier, TaxRate, Unit } from "@/types/api"

const STALE = 60_000

export const useCategories = (includeInactive = false) =>
  useQuery({ queryKey: ["categories", includeInactive], queryFn: () => api.get<Category[]>("/categories", { include_inactive: includeInactive }), staleTime: STALE })
export const useBrands = () => useQuery({ queryKey: ["brands"], queryFn: () => api.get<Brand[]>("/brands"), staleTime: STALE })
export const useUnits = () => useQuery({ queryKey: ["units"], queryFn: () => api.get<Unit[]>("/units"), staleTime: STALE })
export const useTaxRates = () => useQuery({ queryKey: ["tax-rates"], queryFn: () => api.get<TaxRate[]>("/tax-rates"), staleTime: STALE })
export const usePaymentMethods = (includeInactive = false) =>
  useQuery({ queryKey: ["payment-methods", includeInactive], queryFn: () => api.get<PaymentMethod[]>("/payment-methods", { include_inactive: includeInactive }), staleTime: STALE })

export async function searchProducts(q: string): Promise<Option[]> {
  const res = await api.get<Page<Product>>("/products", { search: q, page_size: 20, is_active: true })
  return res.items.map((p) => ({ id: p.id, label: p.name, hint: `${p.sku} · stock ${p.current_stock}` }))
}

export async function searchCustomers(q: string): Promise<Option[]> {
  const res = await api.get<Page<Customer>>("/customers", { search: q, page_size: 20, is_active: true })
  return res.items.map((c) => ({ id: c.id, label: c.name, hint: c.phone ?? c.code }))
}

export async function searchSuppliers(q: string): Promise<Option[]> {
  const res = await api.get<Page<Supplier>>("/suppliers", { search: q, page_size: 20, is_active: true })
  return res.items.map((s) => ({ id: s.id, label: s.name, hint: s.phone ?? s.code }))
}

/** Converts a form input value to number | undefined for react-hook-form's setValueAs. */
export const optionalNumber = (v: unknown): number | undefined => (v === "" || v === null || v === undefined || Number.isNaN(Number(v)) ? undefined : Number(v))
