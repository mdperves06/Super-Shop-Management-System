import { RequirePermission } from "@/components/shared/ui-parts"
import { DiscountRequestsList } from "@/features/sales/discount-requests"

export const metadata = { title: "Discount approvals" }

export default function Page() {
  return <RequirePermission any={["discount.approve", "sale.create"]}><DiscountRequestsList /></RequirePermission>
}
