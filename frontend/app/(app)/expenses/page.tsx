import { RequirePermission } from "@/components/shared/ui-parts"
import { ExpensesPage } from "@/features/finance/finance-pages"

export const metadata = { title: "Expenses" }

export default function Page() {
  return <RequirePermission any={["expense.read"]}><ExpensesPage /></RequirePermission>
}
