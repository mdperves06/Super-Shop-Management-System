"use client"

import { Check, X } from "lucide-react"
import { useState } from "react"

import { DataTable } from "@/components/shared/data-table"
import { ConfirmDialog } from "@/components/shared/dialogs"
import { Money, NativeSelect, PageHeader, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDateTime } from "@/lib/format"
import type { DiscountRequest } from "@/types/api"

/** Managers review cashiers' over-limit discount requests here; cashiers see the outcome of their own. */
export function DiscountRequestsList() {
  const { can, user } = useAuth()
  const canDecide = can("discount.approve")
  const [status, setStatus] = useState("PENDING")
  const [deciding, setDeciding] = useState<{ row: DiscountRequest; approve: boolean } | null>(null)
  const { query, data, setPage } = useTableQuery<DiscountRequest>("discount-requests", "/discount-requests", { filters: { status: status || undefined } })
  const decide = useApiMutation(
    ({ id, approve, note }: { id: number; approve: boolean; note?: string }) => api.post<DiscountRequest>(`/discount-requests/${id}/${approve ? "approve" : "reject"}`, { note }),
    { success: (r) => (r.status === "APPROVED" ? "Discount approved" : "Discount rejected"), invalidate: [["discount-requests"]] },
  )
  return (
    <>
      <PageHeader title="Discount approvals" description="Discounts above a cashier's limit need a manager's approval. Every decision is audited." />
      <div className="mb-3 flex items-center gap-2">
        <NativeSelect aria-label="Status filter" className="w-44" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All requests</option>
          {["PENDING", "APPROVED", "REJECTED", "USED", "EXPIRED"].map((s) => <option key={s} value={s}>{s.charAt(0) + s.slice(1).toLowerCase()}</option>)}
        </NativeSelect>
      </div>
      <DataTable<DiscountRequest>
        page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(r) => r.id}
        empty={{ title: "No discount requests.", description: "Requests appear here when a cashier needs approval at the POS." }}
        columns={[
          { id: "date", header: "Requested", cell: (r) => formatDateTime(r.created_at) },
          { id: "by", header: "Cashier", cell: (r) => r.requested_by_name ?? "—" },
          { id: "pct", header: "Discount", align: "right", cell: (r) => <span className="tabular">{r.discount_percent}% · <Money value={r.discount_amount} /></span> },
          { id: "reason", header: "Reason", cell: (r) => <span className="text-muted-foreground">{r.reason}</span>, hideOnMobile: true },
          { id: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
          { id: "by2", header: "Decision", hideOnMobile: true, cell: (r) => (r.decided_by_name ? <span className="text-xs">{r.decided_by_name}{r.decided_at ? ` · ${formatDateTime(r.decided_at)}` : ""}{r.decision_note ? ` — ${r.decision_note}` : ""}</span> : "—") },
          {
            id: "actions", header: "", align: "right",
            cell: (r) => canDecide && r.status === "PENDING" && r.requested_by !== user?.id ? (
              <div className="flex justify-end gap-1.5">
                <Button size="sm" onClick={() => setDeciding({ row: r, approve: true })}><Check className="size-4" /> Approve</Button>
                <Button size="sm" variant="outline" onClick={() => setDeciding({ row: r, approve: false })}><X className="size-4" /> Reject</Button>
              </div>
            ) : null,
          },
        ]}
      />
      {deciding && (
        <ConfirmDialog
          open onOpenChange={(o) => { if (!o) setDeciding(null) }}
          title={deciding.approve ? "Approve this discount?" : "Reject this discount?"}
          description={`${deciding.row.requested_by_name} asked for ${deciding.row.discount_percent}% off: ${deciding.row.reason}`}
          confirmLabel={deciding.approve ? "Approve" : "Reject"} destructive={!deciding.approve}
          reason={{ label: deciding.approve ? "Note (optional)" : "Reason for rejecting", minLength: deciding.approve ? 0 : 3 }}
          onConfirm={(note) => decide.mutateAsync({ id: deciding.row.id, approve: deciding.approve, note })}
        />
      )}
    </>
  )
}
