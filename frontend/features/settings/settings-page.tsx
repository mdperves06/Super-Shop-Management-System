"use client"

import { useRouter, useSearchParams } from "next/navigation"
import { Suspense } from "react"

import { PageHeader, PageLoading, RequirePermission } from "@/components/shared/ui-parts"
import { PaymentMethodSettings, PromotionSettings, TaxSettings, UnitSettings } from "@/features/settings/settings-catalog"
import { BackupSettings, ImportExportSettings } from "@/features/settings/settings-data"
import { GeneralSettings } from "@/features/settings/settings-general"
import { RolesSettings, UsersSettings } from "@/features/settings/settings-users"
import { useAuth } from "@/lib/auth"
import { cn } from "@/lib/utils"

const TABS = [
  { id: "general", label: "Shop & POS", perms: ["settings.read"], render: () => <GeneralSettings /> },
  { id: "tax", label: "Tax / VAT", perms: ["settings.read"], render: () => <TaxSettings /> },
  { id: "payments", label: "Payment methods", perms: ["settings.read"], render: () => <PaymentMethodSettings /> },
  { id: "units", label: "Units", perms: ["settings.read", "category.manage"], render: () => <UnitSettings /> },
  { id: "promotions", label: "Promotions", perms: ["promotion.manage"], render: () => <PromotionSettings /> },
  { id: "users", label: "Users", perms: ["user.read"], render: () => <UsersSettings /> },
  { id: "roles", label: "Roles & permissions", perms: ["role.manage", "user.read"], render: () => <RolesSettings /> },
  { id: "import", label: "Import / export", perms: ["import.manage", "product.import", "customer.import", "report.export"], render: () => <ImportExportSettings /> },
  { id: "backup", label: "Backup & restore", perms: ["backup.manage"], render: () => <BackupSettings /> },
]

function SettingsInner() {
  const { canAny } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const visible = TABS.filter((t) => canAny(...t.perms))
  const active = visible.find((t) => t.id === params.get("tab")) ?? visible[0]
  return (
    <RequirePermission any={TABS.flatMap((t) => t.perms)}>
      <PageHeader title="Settings" description="Configure the shop, taxes, payments, people and data." />
      <div className="grid gap-5 lg:grid-cols-[210px_1fr]">
        <nav aria-label="Settings sections" className="scroll-thin flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
          {visible.map((t) => (
            <button key={t.id} type="button" aria-current={active?.id === t.id ? "page" : undefined} onClick={() => router.replace(`/settings?tab=${t.id}`)}
              className={cn("h-10 shrink-0 rounded-lg px-3 text-left text-sm font-medium whitespace-nowrap transition-colors", active?.id === t.id ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
              {t.label}
            </button>
          ))}
        </nav>
        <div className="min-w-0">{active?.render()}</div>
      </div>
    </RequirePermission>
  )
}

export function SettingsPage() {
  return <Suspense fallback={<PageLoading />}><SettingsInner /></Suspense>
}
