import { RequirePermission } from "@/components/shared/ui-parts"
import { EmployeesList } from "@/features/hr/employees"

export const metadata = { title: "Employees" }

export default function Page() {
  return <RequirePermission any={["employee.read"]}><EmployeesList /></RequirePermission>
}
