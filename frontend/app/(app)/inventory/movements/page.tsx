import { RequirePermission } from "@/components/shared/ui-parts"
import { MovementsPage } from "@/features/inventory/inventory-pages"

export const metadata = { title: "Stock movements" }

export default function Page() {
  return <RequirePermission any={["inventory.read"]}><MovementsPage /></RequirePermission>
}
