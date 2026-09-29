"use client"

import { useQuery } from "@tanstack/react-query"
import { Download, FileSpreadsheet, Printer } from "lucide-react"
import { useState } from "react"

import { AsyncCombobox, type Option } from "@/components/shared/combobox"
import { DataTable } from "@/components/shared/data-table"
import { defaultPeriod, PeriodFilter, periodParams, type PeriodValue } from "@/components/shared/filters"
import { PrintPortal, printPage } from "@/components/shared/print"
import { NativeSelect, PageHeader, RequirePermission, StatCard } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { api, downloadFile } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDate, formatMoney, formatNumber, formatPercent, humanize } from "@/lib/format"
import { searchProducts, searchSuppliers, useCategories, usePaymentMethods } from "@/services/lookups"
import type { Employee, Page, ReportColumn, ReportData } from "@/types/api"

interface ReportDef { name: string; label: string; filters: ("period" | "group" | "category" | "product" | "supplier" | "employee" | "payment" | "days")[] }
interface Group { title: string; description: string; perms: string[]; reports: ReportDef[] }

export const REPORT_GROUPS: Record<string, Group> = {
  sales: {
    title: "Sales reports", description: "Revenue by period, product, category, cashier and payment method.", perms: ["report.sales"],
    reports: [
      { name: "sales-summary", label: "Sales summary", filters: ["period", "group", "employee", "payment"] },
      { name: "sales-by-product", label: "By product", filters: ["period", "category", "product", "employee"] },
      { name: "sales-by-category", label: "By category", filters: ["period", "employee"] },
      { name: "sales-by-employee", label: "By cashier", filters: ["period"] },
      { name: "sales-by-payment-method", label: "By payment method", filters: ["period", "employee"] },
      { name: "sales-by-customer", label: "By customer", filters: ["period"] },
    ],
  },
  purchases: {
    title: "Purchase reports", description: "What you bought, from whom, and what went back.", perms: ["report.purchases"],
    reports: [
      { name: "purchases-by-supplier", label: "By supplier", filters: ["period", "supplier"] },
      { name: "purchases-by-date", label: "By date", filters: ["period", "group"] },
      { name: "purchase-returns", label: "Purchase returns", filters: ["period", "supplier"] },
    ],
  },
  inventory: {
    title: "Inventory reports", description: "Stock levels, valuation, expiry and movement.", perms: ["report.inventory"],
    reports: [
      { name: "inventory-current", label: "Current stock", filters: ["category", "supplier"] },
      { name: "inventory-valuation", label: "Valuation", filters: ["category", "supplier"] },
      { name: "low-stock", label: "Low stock", filters: [] },
      { name: "out-of-stock", label: "Out of stock", filters: [] },
      { name: "expiring", label: "Expiring soon", filters: ["days"] },
      { name: "expired", label: "Expired", filters: [] },
      { name: "stock-movement", label: "Stock movement", filters: ["period", "product", "category"] },
    ],
  },
  profit: { title: "Profit & loss", description: "Revenue, cost of goods, gross profit and net profit after expenses.", perms: ["report.profit"], reports: [{ name: "profit", label: "Profit & loss", filters: ["period", "group"] }] },
  expenses: { title: "Expense reports", description: "Spending by category.", perms: ["report.expenses"], reports: [{ name: "expenses", label: "By category", filters: ["period"] }] },
  "cash-flow": {
    title: "Cash flow & balances", description: "Money in and out, what you owe and what you are owed.", perms: ["report.finance"],
    reports: [
      { name: "cash-flow", label: "Cash flow", filters: ["period"] },
      { name: "payables", label: "Supplier payables", filters: [] },
      { name: "receivables", label: "Customer receivables", filters: [] },
      { name: "cash-registers", label: "Register sessions", filters: ["period"] },
    ],
  },
}

function cell(v: string | number | null | undefined, c: ReportColumn): string {
  if (v === null || v === undefined || v === "") return "—"
  switch (c.type) {
    case "money": return formatMoney(Number(v))
    case "qty": return formatNumber(Number(v))
    case "int": return formatNumber(Number(v), 0)
    case "percent": return formatPercent(Number(v))
    case "date": return formatDate(String(v))
    default: return String(v)
  }
}

const SUMMARY_MONEY = /sales|revenue|cogs|profit|expenses|total|amount|value|gross|discount|tax|returns|net|balance|received|due|inflow|outflow|cash/i

export function ReportsPage({ group }: { group: keyof typeof REPORT_GROUPS }) {
  const g = REPORT_GROUPS[group]
  const { can } = useAuth()
  const allowed = useQuery({ queryKey: ["report-catalog"], queryFn: () => api.get<{ name: string }[]>("/reports"), staleTime: 60_000 })
  const reports = g.reports.filter((r) => !allowed.data || allowed.data.some((a) => a.name === r.name))
  const [name, setName] = useState(g.reports[0].name)
  const def = reports.find((r) => r.name === name) ?? reports[0] ?? g.reports[0]
  const [period, setPeriod] = useState<PeriodValue>(defaultPeriod("this_month"))
  const [groupBy, setGroupBy] = useState("day")
  const [category, setCategory] = useState("")
  const [product, setProduct] = useState<Option | null>(null)
  const [supplier, setSupplier] = useState<Option | null>(null)
  const [employee, setEmployee] = useState("")
  const [payment, setPayment] = useState("")
  const [days, setDays] = useState("30")
  const cats = useCategories()
  const methods = usePaymentMethods()
  const employees = useQuery({ queryKey: ["employees", "options"], queryFn: () => api.get<Page<Employee>>("/employees", { page_size: 100 }), enabled: def?.filters.includes("employee") && can("employee.read"), staleTime: 60_000 })

  const params = ((): Record<string, string | number | undefined> => {
    const f = def?.filters ?? []
    const p: Record<string, string | number | undefined> = {}
    if (f.includes("period")) Object.assign(p, periodParams(period))
    if (f.includes("group")) p.group_by = groupBy
    if (f.includes("category") && category) p.category_id = Number(category)
    if (f.includes("product") && product) p.product_id = product.id
    if (f.includes("supplier") && supplier) p.supplier_id = supplier.id
    if (f.includes("employee") && employee) p.employee_id = Number(employee)
    if (f.includes("payment") && payment) p.payment_method_id = Number(payment)
    if (f.includes("days") && days) p.days = Number(days)
    return p
  })()

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["report", def?.name, params],
    queryFn: () => api.get<ReportData>(`/reports/${def!.name}`, { ...params, limit: 1000 }),
    enabled: !!def && (!allowed.isLoading),
    placeholderData: (prev) => prev,
  })
  const canExport = can("report.export")
  const page = data ? { items: data.rows, total: data.rows.length, page: 1, page_size: data.rows.length || 1, pages: 1 } : undefined

  return (
    <RequirePermission any={g.perms}>
      <PageHeader title={g.title} description={g.description}
        actions={<>
          {canExport && <Button variant="outline" onClick={() => void downloadFile(`/reports/${def.name}`, `${def.name}.csv`, { ...params, format: "csv", limit: 5000 })}><Download className="size-4" /> CSV</Button>}
          {canExport && <Button variant="outline" onClick={() => void downloadFile(`/reports/${def.name}`, `${def.name}.xlsx`, { ...params, format: "xlsx", limit: 5000 })}><FileSpreadsheet className="size-4" /> Excel</Button>}
          <Button variant="outline" onClick={() => printPage("size: A4 landscape; margin: 10mm")} disabled={!data}><Printer className="size-4" /> Print</Button>
        </>} />

      {reports.length > 1 && (
        <div className="scroll-thin mb-4 flex gap-1 overflow-x-auto rounded-xl bg-muted p-1" role="tablist" aria-label="Report">
          {reports.map((r) => (
            <button key={r.name} role="tab" aria-selected={def?.name === r.name} onClick={() => setName(r.name)}
              className={`h-9 shrink-0 rounded-lg px-4 text-sm font-medium whitespace-nowrap ${def?.name === r.name ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>{r.label}</button>
          ))}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-end gap-2">
        {def?.filters.includes("period") && <PeriodFilter value={period} onChange={setPeriod} />}
        {def?.filters.includes("group") && <NativeSelect aria-label="Group by" value={groupBy} onChange={(e) => setGroupBy(e.target.value)} className="w-32"><option value="day">Daily</option><option value="week">Weekly</option><option value="month">Monthly</option><option value="year">Yearly</option></NativeSelect>}
        {def?.filters.includes("category") && <NativeSelect aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} className="w-44"><option value="">All categories</option>{cats.data?.filter((c) => c.parent_id === null).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect>}
        {def?.filters.includes("product") && <div className="w-56"><AsyncCombobox value={product} onChange={setProduct} fetcher={searchProducts} queryKey="products" placeholder="Any product" /></div>}
        {def?.filters.includes("supplier") && <div className="w-56"><AsyncCombobox value={supplier} onChange={setSupplier} fetcher={searchSuppliers} queryKey="suppliers" placeholder="Any supplier" /></div>}
        {def?.filters.includes("employee") && can("employee.read") && <NativeSelect aria-label="Cashier" value={employee} onChange={(e) => setEmployee(e.target.value)} className="w-44"><option value="">All cashiers</option>{employees.data?.items.filter((e) => e.user_id).map((e) => <option key={e.id} value={e.user_id!}>{e.full_name}</option>)}</NativeSelect>}
        {def?.filters.includes("payment") && <NativeSelect aria-label="Payment method" value={payment} onChange={(e) => setPayment(e.target.value)} className="w-44"><option value="">All methods</option>{methods.data?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</NativeSelect>}
        {def?.filters.includes("days") && <NativeSelect aria-label="Window" value={days} onChange={(e) => setDays(e.target.value)} className="w-40">{[7, 15, 30, 60, 90].map((d) => <option key={d} value={d}>Next {d} days</option>)}</NativeSelect>}
      </div>

      {data && Object.keys(data.summary).length > 0 && (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
          {Object.entries(data.summary).map(([k, v]) => (
            <StatCard key={k} label={humanize(k)} value={typeof v === "number" ? (k.includes("percent") ? formatPercent(v) : SUMMARY_MONEY.test(k) ? formatMoney(v) : formatNumber(v)) : String(v)} />
          ))}
        </div>
      )}
      {isLoading && !data && <Skeleton className="mb-4 h-24 w-full" />}

      <DataTable<Record<string, string | number | null>>
        caption={data?.title} page={page} isLoading={isLoading} isFetching={isFetching} error={error} onRetry={() => refetch()} rowKey={(r) => JSON.stringify(r)}
        empty={{ title: "No data for these filters.", description: "Try a wider date range or fewer filters." }}
        columns={(data?.columns ?? []).map((c) => ({ id: c.key, header: c.label, align: ["money", "qty", "int", "percent"].includes(c.type) ? ("right" as const) : ("left" as const), cell: (r: Record<string, string | number | null>) => <span className={["money", "qty", "int", "percent"].includes(c.type) ? "tabular" : undefined}>{cell(r[c.key], c)}</span> }))}
      />

      {data && (
        <PrintPortal>
          <h1 style={{ fontSize: 18, fontWeight: 700 }}>{data.title}</h1>
          {data.period && <p style={{ marginBottom: 8 }}>{formatDate(data.period.start)} – {formatDate(data.period.end)}</p>}
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead><tr>{data.columns.map((c) => <th key={c.key} style={{ borderBottom: "2px solid #000", padding: "3px 6px", textAlign: ["money", "qty", "int", "percent"].includes(c.type) ? "right" : "left" }}>{c.label}</th>)}</tr></thead>
            <tbody>{data.rows.map((r, i) => <tr key={i}>{data.columns.map((c) => <td key={c.key} style={{ borderBottom: "1px solid #ccc", padding: "3px 6px", textAlign: ["money", "qty", "int", "percent"].includes(c.type) ? "right" : "left" }}>{cell(r[c.key], c)}</td>)}</tr>)}</tbody>
          </table>
          {Object.keys(data.summary).length > 0 && <p style={{ marginTop: 10, fontSize: 11 }}>{Object.entries(data.summary).map(([k, v]) => `${humanize(k)}: ${typeof v === "number" ? (SUMMARY_MONEY.test(k) ? formatMoney(v) : formatNumber(v)) : v}`).join("   ·   ")}</p>}
        </PrintPortal>
      )}
    </RequirePermission>
  )
}
