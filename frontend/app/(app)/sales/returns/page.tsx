import { RequirePermission } from "@/components/shared/ui-parts"
import { ReturnsList } from "@/features/sales/sales-pages"

export const metadata = { title: "Sale returns" }

export default function Page() {
  return <RequirePermission any={["sale.read"]}><ReturnsList /></RequirePermission>
}
