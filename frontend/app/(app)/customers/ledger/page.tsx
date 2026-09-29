import { RequirePermission } from "@/components/shared/ui-parts"
import { CustomerLedgerPage } from "@/features/parties/customers"

export const metadata = { title: "Customer ledger" }

export default function Page() {
  return <RequirePermission any={["customer.read"]}><CustomerLedgerPage /></RequirePermission>
}
