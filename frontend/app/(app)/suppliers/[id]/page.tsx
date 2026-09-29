"use client"

import { useParams } from "next/navigation"

import { RequirePermission } from "@/components/shared/ui-parts"
import { SupplierProfilePage } from "@/features/parties/suppliers"

export default function Page() {
  const { id } = useParams<{ id: string }>()
  return <RequirePermission any={["supplier.read"]}><SupplierProfilePage id={Number(id)} /></RequirePermission>
}
