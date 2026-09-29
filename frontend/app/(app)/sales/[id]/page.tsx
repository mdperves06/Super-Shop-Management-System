"use client"

import { useParams } from "next/navigation"

import { RequirePermission } from "@/components/shared/ui-parts"
import { SaleDetail } from "@/features/sales/sales-pages"

export default function Page() {
  const { id } = useParams<{ id: string }>()
  return <RequirePermission any={["sale.read"]}><SaleDetail id={Number(id)} /></RequirePermission>
}
