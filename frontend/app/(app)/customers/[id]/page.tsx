"use client"

import { useParams } from "next/navigation"

import { RequirePermission } from "@/components/shared/ui-parts"
import { CustomerProfilePage } from "@/features/parties/customers"

export default function Page() {
  const { id } = useParams<{ id: string }>()
  return <RequirePermission any={["customer.read"]}><CustomerProfilePage id={Number(id)} /></RequirePermission>
}
