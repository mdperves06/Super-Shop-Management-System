import { RequirePermission } from "@/components/shared/ui-parts"
import { SupplierLedgerPage } from "@/features/parties/suppliers"

export const metadata = { title: "Supplier ledger" }

export default function Page() {
  return <RequirePermission any={["supplier.read"]}><SupplierLedgerPage /></RequirePermission>
}
