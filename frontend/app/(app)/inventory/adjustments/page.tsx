import { RequirePermission } from "@/components/shared/ui-parts"
import { AdjustmentsPage } from "@/features/inventory/inventory-pages"

export const metadata = { title: "Stock adjustments" }

export default function Page() {
  return <RequirePermission any={["inventory.read"]}><AdjustmentsPage /></RequirePermission>
}
