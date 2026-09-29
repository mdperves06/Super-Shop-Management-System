import { RequirePermission } from "@/components/shared/ui-parts"
import { CustomersList } from "@/features/parties/customers"

export const metadata = { title: "Customers" }

export default function Page() {
  return <RequirePermission any={["customer.read"]}><CustomersList /></RequirePermission>
}
