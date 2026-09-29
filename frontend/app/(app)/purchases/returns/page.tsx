import { RequirePermission } from "@/components/shared/ui-parts"
import { PurchaseReturnsPage } from "@/features/purchasing/purchase-returns"

export const metadata = { title: "Purchase returns" }

export default function Page() {
  return <RequirePermission any={["purchase.read"]}><PurchaseReturnsPage /></RequirePermission>
}
