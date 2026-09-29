import { PageHeader, RequirePermission } from "@/components/shared/ui-parts"
import { PurchaseForm } from "@/features/purchasing/purchase-form"

export const metadata = { title: "New purchase order" }

export default function Page() {
  return (
    <RequirePermission any={["purchase.create"]}>
      <PageHeader back={{ href: "/purchases", label: "Purchase orders" }} title="New purchase order" description="Choose a supplier and the products to order." />
      <PurchaseForm />
    </RequirePermission>
  )
}
