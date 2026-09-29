import { RequirePermission } from "@/components/shared/ui-parts"
import { StockPage } from "@/features/inventory/inventory-pages"

export const metadata = { title: "Stock" }

export default function Page() {
  return <RequirePermission any={["inventory.read"]}><StockPage /></RequirePermission>
}
