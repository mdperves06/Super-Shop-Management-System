import type { Metadata } from "next"

import { RequirePermission } from "@/components/shared/ui-parts"
import { DashboardView } from "@/features/dashboard/dashboard-view"

export const metadata: Metadata = { title: "Dashboard" }

export default function DashboardPage() {
  return (
    <RequirePermission any={["dashboard.view"]}>
      <DashboardView />
    </RequirePermission>
  )
}
