"use client"

import { AlertOctagon, AlertTriangle, BellRing, CheckCheck, Info } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { DateRangeFilter, type DateRange } from "@/components/shared/filters"
import { NativeSelect, PageHeader, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api } from "@/lib/api"
import { formatDateTime, humanize } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { AuditLog, Notification } from "@/types/api"

const ICON = { critical: AlertOctagon, warning: AlertTriangle, info: Info } as const
const TONE = { critical: "text-destructive bg-destructive/10", warning: "text-warning bg-warning/15", info: "text-info bg-info/10" } as const
const TYPES = ["low_stock", "out_of_stock", "expiring", "expired", "pending_purchase", "large_discount", "cash_discrepancy", "payment_due", "supplier_due"]

const HREF: Record<string, (n: Notification) => string | null> = {
  product: (n) => `/products/${n.entity_id}`, batch: () => "/inventory/expiring", purchase: (n) => `/purchases/${n.entity_id}`, supplier: (n) => `/suppliers/${n.entity_id}`,
  customer: (n) => `/customers/${n.entity_id}`, sale: (n) => `/sales/${n.entity_id}`, cash_session: () => "/cash-register",
}

export function NotificationsPage() {
  const [unread, setUnread] = useState(false)
  const [type, setType] = useState("")
  const { query, data, setPage } = useTableQuery<Notification>("notifications", "/notifications", { filters: { unread_only: unread || undefined, type: type || undefined }, pageSize: 25 })
  const refresh = [["notifications"], ["notifications", "count"]]
  const read = useApiMutation((id: number) => api.post(`/notifications/${id}/read`), { invalidate: refresh })
  const readAll = useApiMutation(() => api.post("/notifications/read-all"), { success: "All notifications marked as read", invalidate: refresh })
  return (
    <>
      <PageHeader title="Notifications" description="Stock, expiry, payment and cash alerts for your role."
        actions={<Button variant="outline" onClick={() => readAll.mutate()} disabled={readAll.isPending}><CheckCheck className="size-4" /> Mark all as read</Button>} />
      <Toolbar>
        <NativeSelect aria-label="Type" value={type} onChange={(e) => setType(e.target.value)} className="w-52"><option value="">All types</option>{TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}</NativeSelect>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" checked={unread} onChange={(e) => setUnread(e.target.checked)} /> Unread only</label>
      </Toolbar>
      {query.isLoading ? <DataTable<Notification> columns={[{ id: "x", header: "", cell: () => null }]} isLoading rowKey={(n) => n.id} /> : (data?.items.length ?? 0) === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed bg-card py-16 text-center"><BellRing className="size-8 text-muted-foreground" /><p className="font-medium">You’re all caught up.</p><p className="text-sm text-muted-foreground">New alerts appear here as stock and payments change.</p></div>
      ) : (
        <>
          <ul className="divide-y overflow-hidden rounded-xl border bg-card">
            {data!.items.map((n) => {
              const Icon = ICON[n.severity as keyof typeof ICON] ?? Info
              const href = n.entity ? HREF[n.entity]?.(n) : null
              return (
                <li key={n.id} className={cn("flex items-start gap-3 px-4 py-3", !n.is_read && "bg-primary/5")}>
                  <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg", TONE[n.severity as keyof typeof TONE] ?? TONE.info)}><Icon className="size-4" /></span>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 text-sm font-medium">{n.title}{!n.is_read && <span className="size-2 rounded-full bg-primary" aria-label="unread" />}</p>
                    <p className="text-sm text-muted-foreground">{n.message}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(n.created_at)}</p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    {href && <Button variant="outline" size="sm" render={<Link href={href} />} onClick={() => !n.is_read && read.mutate(n.id)}>View</Button>}
                    {!n.is_read && <Button variant="ghost" size="sm" onClick={() => read.mutate(n.id)}>Mark read</Button>}
                  </div>
                </li>
              )
            })}
          </ul>
          {data && data.pages > 1 && (
            <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground"><span>{data.total} notifications</span>
              <span className="flex items-center gap-2"><Button variant="outline" size="sm" disabled={data.page <= 1} onClick={() => setPage(data.page - 1)}>Previous</Button>{data.page} / {data.pages}<Button variant="outline" size="sm" disabled={data.page >= data.pages} onClick={() => setPage(data.page + 1)}>Next</Button></span></div>
          )}
        </>
      )}
    </>
  )
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  if (value === null || value === undefined) return null
  return (
    <div>
      <p className="mb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</p>
      <pre className="scroll-thin max-h-56 overflow-auto rounded-lg bg-muted p-3 text-xs">{JSON.stringify(value, null, 2)}</pre>
    </div>
  )
}

export function AuditLogsPage() {
  const [entity, setEntity] = useState("")
  const [action, setAction] = useState("")
  const [range, setRange] = useState<DateRange>({ start: "", end: "" })
  const [detail, setDetail] = useState<AuditLog | null>(null)
  const ok = !!range.start && !!range.end
  const { query, data, setPage, search, setSearch } = useTableQuery<AuditLog>("audit-logs", "/audit-logs", {
    filters: { entity: entity || undefined, action: action || undefined, start: ok ? range.start : undefined, end: ok ? range.end : undefined }, pageSize: 30,
  })
  return (
    <>
      <PageHeader title="Audit logs" description="A read-only record of sensitive actions: price changes, voids, adjustments, approvals and sign-ins." />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search action, user or description…" />
        <NativeSelect aria-label="Entity" value={entity} onChange={(e) => setEntity(e.target.value)} className="w-40"><option value="">All records</option>{["product", "sale", "sale_return", "purchase", "purchase_return", "supplier", "customer", "user", "role", "settings", "cash_session", "expense", "employee"].map((e) => <option key={e} value={e}>{humanize(e)}</option>)}</NativeSelect>
        <NativeSelect aria-label="Action type" value={action} onChange={(e) => setAction(e.target.value)} className="w-48"><option value="">All actions</option>{["product.price_change", "sale.void", "inventory.adjust", "purchase.approve", "supplier.balance_adjust", "settings.update", "auth.login", "register.close"].map((a) => <option key={a} value={a}>{humanize(a)}</option>)}</NativeSelect>
        <DateRangeFilter value={range} onChange={setRange} />
      </Toolbar>
      <DataTable<AuditLog>
        caption="Audit log" page={data} isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(l) => l.id} onRowClick={setDetail}
        empty={{ title: "No audit entries match." }}
        columns={[
          { id: "time", header: "When", cell: (l) => <span className="whitespace-nowrap">{formatDateTime(l.created_at)}</span> },
          { id: "user", header: "Who", cell: (l) => l.user_email ?? <span className="text-muted-foreground">system</span> },
          { id: "action", header: "Action", cell: (l) => <StatusBadge status={l.action} label={humanize(l.action)} tone={/void|delete|lockout|restore/.test(l.action) ? "danger" : /price|adjust|balance|discrepancy|settings/.test(l.action) ? "warning" : "neutral"} /> },
          { id: "entity", header: "Record", cell: (l) => <span className="text-muted-foreground">{humanize(l.entity)}{l.entity_id ? ` #${l.entity_id}` : ""}</span>, hideOnMobile: true },
          { id: "ip", header: "IP", cell: (l) => <span className="font-mono text-xs text-muted-foreground">{l.ip_address ?? "—"}</span>, hideOnMobile: true },
        ]}
      />
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader><DialogTitle>{detail && humanize(detail.action)}</DialogTitle><DialogDescription>{detail && `${detail.user_email ?? "system"} · ${formatDateTime(detail.created_at)} · ${humanize(detail.entity)}${detail.entity_id ? ` #${detail.entity_id}` : ""}`}</DialogDescription></DialogHeader>
          {detail?.description && <p className="text-sm">{detail.description}</p>}
          <div className="grid gap-3 sm:grid-cols-2"><JsonBlock title="Before" value={detail?.old_value} /><JsonBlock title="After" value={detail?.new_value} /></div>
          {!detail?.old_value && !detail?.new_value && <p className="text-sm text-muted-foreground">No before/after values were recorded for this action.</p>}
        </DialogContent>
      </Dialog>
    </>
  )
}
