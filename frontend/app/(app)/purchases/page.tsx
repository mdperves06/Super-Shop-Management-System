import { RequirePermission } from "@/components/shared/ui-parts"
import { PurchasesList } from "@/features/purchasing/purchases-list"

export const metadata = { title: "Purchase orders" }

export default function Page() {
  return <RequirePermission any={["purchase.read"]}><PurchasesList /></RequirePermission>
}
