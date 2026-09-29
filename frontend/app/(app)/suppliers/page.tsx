import { RequirePermission } from "@/components/shared/ui-parts"
import { SuppliersList } from "@/features/parties/suppliers"

export const metadata = { title: "Suppliers" }

export default function Page() {
  return <RequirePermission any={["supplier.read"]}><SuppliersList /></RequirePermission>
}
