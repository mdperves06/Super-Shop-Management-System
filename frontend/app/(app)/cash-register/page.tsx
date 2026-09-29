import { RequirePermission } from "@/components/shared/ui-parts"
import { CashRegisterPage } from "@/features/finance/finance-pages"

export const metadata = { title: "Cash register" }

export default function Page() {
  return <RequirePermission any={["register.use", "register.manage"]}><CashRegisterPage /></RequirePermission>
}
