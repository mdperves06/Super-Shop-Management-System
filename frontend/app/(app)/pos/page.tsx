import { RequirePermission } from "@/components/shared/ui-parts"
import { PosScreen } from "@/features/pos/pos-screen"

export const metadata = { title: "POS" }

export default function Page() {
  return <RequirePermission any={["sale.create"]}><PosScreen /></RequirePermission>
}
