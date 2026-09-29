"use client"

import { Plus } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { DateRangeFilter, type DateRange } from "@/components/shared/filters"
import { Can, Money, NativeSelect, PageHeader, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { useTableQuery } from "@/hooks/use-table-query"
import { useAuth } from "@/lib/auth"
import { formatDate } from "@/lib/format"
import type { Purchase } from "@/types/api"

const STATUSES = ["DRAFT", "PENDING", "APPROVED", "PARTIALLY_RECEIVED", "RECEIVED", "CANCELLED"]

export function PurchasesList({ receiveMode }: { receiveMode?: boolean }) {
  const router = useRouter()
  const { can } = useAuth()
  const [status, setStatus] = useState(receiveMode ? "" : "")
  const [range, setRange] = useState<DateRange>({ start: "", end: "" })
  const { query, data, setPage, search, setSearch, sort, toggleSort } = useTableQuery<Purchase>(receiveMode ? "purchases-receive" : "purchases", "/purchases", {
    filters: { status: status || undefined, start: range.start || undefined, end: range.end || undefined },
    defaultSort: "-order_date",
  })
  // In "Receive stock" mode show only orders that can still receive goods
  const items = receiveMode ? data?.items.filter((p) => p.status === "APPROVED" || p.status === "PARTIALLY_RECEIVED") : data?.items
  const page = data && items ? { ...data, items } : data

  return (
    <>
      <PageHeader
        title={receiveMode ? "Receive stock" : "Purchase orders"}
        description={receiveMode ? "Approved orders waiting for goods. Open one to record what arrived — stock and the supplier payable are created on receipt." : "Order from suppliers, track approval and receipt."}
        actions={<Can perm="purchase.create"><Button render={<Link href="/purchases/new" />}><Plus className="size-4" /> New purchase order</Button></Can>}
      />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search PO number or supplier…" />
        {!receiveMode && <NativeSelect aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-48"><option value="">All statuses</option>{STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}</option>)}</NativeSelect>}
        <DateRangeFilter value={range} onChange={setRange} />
      </Toolbar>
      <DataTable<Purchase>
        caption="Purchase orders"
        page={page} isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} sort={sort} onSort={toggleSort}
        rowKey={(p) => p.id} onRowClick={(p) => router.push(`/purchases/${p.id}`)}
        empty={{
          title: receiveMode ? "Nothing waiting to be received." : "No purchase orders found.",
          description: receiveMode ? "Approve a purchase order and it will appear here." : "Create a purchase order to restock from a supplier.",
          action: can("purchase.create") && !receiveMode ? <Button render={<Link href="/purchases/new" />}><Plus className="size-4" /> New purchase order</Button> : undefined,
        }}
        columns={[
          { id: "po", header: "PO number", sortKey: "po_number", cell: (p) => <span className="font-mono text-xs font-medium">{p.po_number}</span> },
          { id: "date", header: "Date", sortKey: "order_date", cell: (p) => formatDate(p.order_date) },
          { id: "supplier", header: "Supplier", cell: (p) => <span className="font-medium">{p.supplier_name}</span> },
          { id: "items", header: "Items", align: "right", cell: (p) => p.items.length, hideOnMobile: true },
          { id: "total", header: "Total", sortKey: "total_amount", align: "right", cell: (p) => <Money value={p.total_amount} className="font-medium" /> },
          { id: "received", header: "Received", align: "right", cell: (p) => <Money value={p.received_value} className="text-muted-foreground" />, hideOnMobile: true },
          { id: "status", header: "Status", cell: (p) => <StatusBadge status={p.status} /> },
        ]}
      />
    </>
  )
}
