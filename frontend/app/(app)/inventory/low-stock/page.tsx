import { RequirePermission } from "@/components/shared/ui-parts"
import { LowStockPage } from "@/features/inventory/inventory-pages"

export const metadata = { title: "Low stock" }

export default function Page() {
  return <RequirePermission any={["inventory.read"]}><LowStockPage /></RequirePermission>
}
