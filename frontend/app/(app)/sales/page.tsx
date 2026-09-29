import { RequirePermission } from "@/components/shared/ui-parts"
import { SalesList } from "@/features/sales/sales-pages"

export const metadata = { title: "Sales" }

export default function Page() {
  return <RequirePermission any={["sale.read"]}><SalesList /></RequirePermission>
}
