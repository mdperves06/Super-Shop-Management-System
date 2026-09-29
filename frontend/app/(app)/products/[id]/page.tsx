"use client"

import { useParams } from "next/navigation"

import { RequirePermission } from "@/components/shared/ui-parts"
import { ProductDetail } from "@/features/products/product-detail"

export default function Page() {
  const { id } = useParams<{ id: string }>()
  return <RequirePermission any={["product.read"]}><ProductDetail id={Number(id)} /></RequirePermission>
}
