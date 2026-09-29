import { RequirePermission } from "@/components/shared/ui-parts"
import { ExpiredPage } from "@/features/inventory/inventory-pages"

export const metadata = { title: "Expired stock" }

export default function Page() {
  return <RequirePermission any={["inventory.read"]}><ExpiredPage /></RequirePermission>
}
