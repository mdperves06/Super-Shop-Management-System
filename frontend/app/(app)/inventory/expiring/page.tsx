import { RequirePermission } from "@/components/shared/ui-parts"
import { ExpiringPage } from "@/features/inventory/inventory-pages"

export const metadata = { title: "Expiring stock" }

export default function Page() {
  return <RequirePermission any={["inventory.read"]}><ExpiringPage /></RequirePermission>
}
