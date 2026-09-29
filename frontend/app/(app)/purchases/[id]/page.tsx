"use client"

import { useParams } from "next/navigation"

import { RequirePermission } from "@/components/shared/ui-parts"
import { PurchaseDetail } from "@/features/purchasing/purchase-detail"

export default function Page() {
  const { id } = useParams<{ id: string }>()
  return <RequirePermission any={["purchase.read"]}><PurchaseDetail id={Number(id)} /></RequirePermission>
}
