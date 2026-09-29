import { RequirePermission } from "@/components/shared/ui-parts"
import { AuditLogsPage } from "@/features/system/notifications-audit"

export const metadata = { title: "Audit logs" }

export default function Page() {
  return <RequirePermission any={["audit.read"]}><AuditLogsPage /></RequirePermission>
}
