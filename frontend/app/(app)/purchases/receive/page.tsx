import { RequirePermission } from "@/components/shared/ui-parts"
import { PurchasesList } from "@/features/purchasing/purchases-list"

export const metadata = { title: "Receive stock" }

export default function Page() {
  return <RequirePermission any={["purchase.receive", "purchase.read"]}><PurchasesList receiveMode /></RequirePermission>
}
