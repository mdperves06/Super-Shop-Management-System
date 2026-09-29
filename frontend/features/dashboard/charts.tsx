"use client"

import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { formatMoney, formatNumber } from "@/lib/format"
import type { Dashboard } from "@/types/api"

const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"]
const STATUS_COLORS: Record<string, string> = {
  Healthy: "var(--success)", "Low stock": "var(--warning)", "Out of stock": "var(--destructive)", "Expiring soon": "var(--chart-3)", Expired: "var(--chart-4)",
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

export function bucketLabel(bucket: string, granularity: string): string {
  if (granularity === "hour") {
    const h = Number(bucket.slice(11, 13))
    return `${h % 12 === 0 ? 12 : h % 12}${h < 12 ? "am" : "pm"}`
  }
  if (granularity === "day") return `${Number(bucket.slice(8, 10))} ${MONTHS[Number(bucket.slice(5, 7)) - 1]}`
  if (granularity === "week") return `Wk ${Number(bucket.slice(8, 10))} ${MONTHS[Number(bucket.slice(5, 7)) - 1]}`
  if (granularity === "month") return `${MONTHS[Number(bucket.slice(5, 7)) - 1]} ${bucket.slice(2, 4)}`
  return bucket
}

const axisProps = { tick: { fontSize: 11, fill: "var(--muted-foreground)" }, tickLine: false, axisLine: false } as const

function tooltipStyle() {
  return { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--popover-foreground)" }
}

function Empty({ text = "No data for this period" }: { text?: string }) {
  return <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">{text}</div>
}

const moneyAxis = (v: number) => formatMoney(v, { symbol: false, compact: true }).replace(".00", "")

export function SalesChart({ data, granularity }: { data: Dashboard["series"]; granularity: string }) {
  if (data.length === 0 || data.every((d) => d.sales === 0)) return <Empty />
  const rows = data.map((d) => ({ ...d, label: bucketLabel(d.bucket, granularity) }))
  return (
    <div role="img" aria-label={`Sales over time, total ${formatMoney(rows.reduce((s, r) => s + r.sales, 0))}`} className="h-64 w-full">
      <ResponsiveContainer>
        <AreaChart data={rows} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="salesFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.35} />
              <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={16} />
          <YAxis {...axisProps} width={52} tickFormatter={moneyAxis} />
          <Tooltip contentStyle={tooltipStyle()} formatter={(v) => [formatMoney(Number(v)), "Sales"]} />
          <Area type="monotone" dataKey="sales" stroke="var(--chart-1)" strokeWidth={2} fill="url(#salesFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ProfitChart({ data, granularity }: { data: Dashboard["series"]; granularity: string }) {
  if (data.length === 0 || data.every((d) => !d.revenue)) return <Empty />
  const rows = data.map((d) => ({ ...d, label: bucketLabel(d.bucket, granularity) }))
  return (
    <div role="img" aria-label="Revenue, cost of goods and profit over time" className="h-64 w-full">
      <ResponsiveContainer>
        <ComposedChart data={rows} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={16} />
          <YAxis {...axisProps} width={52} tickFormatter={moneyAxis} />
          <Tooltip contentStyle={tooltipStyle()} formatter={(v, name) => [formatMoney(Number(v)), String(name)]} />
          <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="revenue" name="Revenue" fill="var(--chart-1)" fillOpacity={0.85} radius={[3, 3, 0, 0]} maxBarSize={28} />
          <Bar dataKey="cogs" name="Cost" fill="var(--chart-3)" fillOpacity={0.85} radius={[3, 3, 0, 0]} maxBarSize={28} />
          <Line type="monotone" dataKey="profit" name="Profit" stroke="var(--success)" strokeWidth={2.5} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

export function TopProductsChart({ data }: { data: Dashboard["top_products"] }) {
  if (data.length === 0) return <Empty text="No sales in this period" />
  const rows = data.map((d) => ({ ...d, short: d.name.length > 22 ? `${d.name.slice(0, 21)}…` : d.name }))
  const height = Math.max(256, rows.length * 30)
  return (
    <div role="img" aria-label="Top selling products by quantity" style={{ height }} className="w-full">
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis type="number" {...axisProps} allowDecimals={false} />
          <YAxis type="category" dataKey="short" width={140} {...axisProps} />
          <Tooltip contentStyle={tooltipStyle()} formatter={(v, name) => [name === "quantity" ? formatNumber(Number(v)) : formatMoney(Number(v)), name === "quantity" ? "Units sold" : "Revenue"]} cursor={{ fill: "var(--muted)" }} />
          <Bar dataKey="quantity" fill="var(--chart-1)" radius={[0, 4, 4, 0]} maxBarSize={18} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function Donut({ rows, colors, label }: { rows: { name: string; value: number }[]; colors: (name: string, i: number) => string; label: string }) {
  const total = rows.reduce((s, r) => s + r.value, 0)
  return (
    <div role="img" aria-label={label} className="flex flex-col items-center gap-2">
      <div className="h-44 w-full">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={rows} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="88%" paddingAngle={2} stroke="var(--card)" strokeWidth={2}>
              {rows.map((r, i) => <Cell key={r.name} fill={colors(r.name, i)} />)}
            </Pie>
            <Tooltip contentStyle={tooltipStyle()} formatter={(v, n) => [`${formatNumber(Number(v))} (${total ? Math.round((Number(v) / total) * 100) : 0}%)`, String(n)]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="grid w-full grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        {rows.map((r, i) => (
          <li key={r.name} className="flex items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1.5"><span className="size-2.5 shrink-0 rounded-full" style={{ background: colors(r.name, i) }} /><span className="truncate">{r.name}</span></span>
            <span className="tabular text-muted-foreground">{formatNumber(r.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function CategoryDonut({ data }: { data: Dashboard["category_sales"] }) {
  if (data.length === 0) return <Empty text="No sales in this period" />
  const top = data.slice(0, 5)
  const rest = data.slice(5).reduce((s, d) => s + d.amount, 0)
  const rows = [...top.map((d) => ({ name: d.category, value: Math.round(d.amount) })), ...(rest > 0 ? [{ name: "Other", value: Math.round(rest) }] : [])]
  return <Donut rows={rows} colors={(n, i) => (n === "Other" ? "var(--muted-foreground)" : COLORS[i % COLORS.length])} label="Sales share by category" />
}

export function InventoryDonut({ data }: { data: NonNullable<Dashboard["inventory_status"]> }) {
  const rows = data.filter((d) => d.count > 0).map((d) => ({ name: d.status, value: d.count }))
  if (rows.length === 0) return <Empty text="No products yet" />
  return <Donut rows={rows} colors={(n) => STATUS_COLORS[n] ?? "var(--muted-foreground)"} label="Inventory health" />
}
