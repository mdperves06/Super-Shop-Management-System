"use client"

import { useParams } from "next/navigation"

import { RequirePermission } from "@/components/shared/ui-parts"
import { EmployeeProfile } from "@/features/hr/employees"

export default function Page() {
  const { id } = useParams<{ id: string }>()
  return <RequirePermission any={["employee.read"]}><EmployeeProfile id={Number(id)} /></RequirePermission>
}
