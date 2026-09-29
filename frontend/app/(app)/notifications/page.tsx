import { RequirePermission } from "@/components/shared/ui-parts"
import { NotificationsPage } from "@/features/system/notifications-audit"

export const metadata = { title: "Notifications" }

export default function Page() {
  return <RequirePermission any={["notification.read"]}><NotificationsPage /></RequirePermission>
}
