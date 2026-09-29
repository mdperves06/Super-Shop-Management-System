"use client"

import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, Banknote, CalendarClock, HandCoins, Package, PiggyBank, ShoppingBag, TrendingUp, Wallet } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { StatusBadge, Money, NativeSelect, PageHeader, SectionCard, StatCard } from "@/components/shared/ui-parts"
import { defaultPeriod, PeriodFilter, periodParams, type PeriodValue } from "@/components/shared/filters"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryDonut, InventoryDonut, ProfitChart, SalesChart, TopProductsChart } from "@/features/dashboard/charts"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format"
import { useT } from "@/lib/i18n"
import type { Dashboard } from "@/types/api"

const RECENT_HREF: Record<string, string> = { sale: "/sales", purchase: "/purchases", return: "/sales/returns" }

export function DashboardView() {
  const t = useT()
  const { can, user } = useAuth()
  const [period, setPeriod] = useState<PeriodValue>(defaultPeriod("today"))
  const [topN, setTopN] = useState(10)
  const [granularity, setGranularity] = useState<string>("auto")
  const finance = can("dashboard.finance")
  const canInventory = can("inventory.read")

  const params = { ...periodParams(period), top_n: topN, granularity: granularity === "auto" ? undefined : granularity }
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", params],
    queryFn: () => api.get<Dashboard>("/dashboard", params),
    refetchInterval: 60_000,
    placeholderData: (prev) => prev,
  })
  const k = data?.kpis
  const loading = isLoading

  return (
    <>
      <PageHeader
        title={t("dashboard.title")}
        description={`Welcome back, ${user?.full_name.split(" ")[0]}. ${data ? `${data.period.start === data.period.end ? data.period.start : `${data.period.start} → ${data.period.end}`}` : ""}`}
        actions={<PeriodFilter value={period} onChange={setPeriod} />}
      />

      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Could not load the dashboard: {error.message} <button className="ml-2 underline" onClick={() => refetch()}>Retry</button>
        </div>
      )}

      <section aria-label="Key figures" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard loading={loading} label={t("dashboard.sales")} value={formatMoney(k?.sales_total)} icon={<ShoppingBag className="size-[18px]" />}
          hint={k ? `${formatNumber(k.invoices, 0)} invoices${k.returns_total ? ` · ${formatMoney(k.returns_total)} returned` : ""}` : undefined} href="/sales" />
        {finance && <StatCard loading={loading} label={t("dashboard.profit")} value={formatMoney(k?.profit)} icon={<TrendingUp className="size-[18px]" />} tone={k && (k.profit ?? 0) < 0 ? "danger" : "neutral"}
          hint={k?.net_profit !== null && k?.net_profit !== undefined ? `Net after expenses ${formatMoney(k.net_profit)}` : undefined} href="/reports/profit" />}
        {finance && <StatCard loading={loading} label={t("dashboard.purchases")} value={formatMoney(k?.purchases)} icon={<Package className="size-[18px]" />} href="/purchases" />}
        {finance && <StatCard loading={loading} label={t("dashboard.stockValue")} value={formatMoney(k?.stock_value)} icon={<PiggyBank className="size-[18px]" />} href="/reports/inventory" />}
        {canInventory && <StatCard loading={loading} label={t("dashboard.lowStock")} value={formatNumber(k?.low_stock, 0)} tone={(k?.low_stock ?? 0) > 0 ? "warning" : "neutral"} icon={<AlertTriangle className="size-[18px]" />}
          hint={k && k.out_of_stock ? `${k.out_of_stock} out of stock` : undefined} href="/inventory/low-stock" />}
        {canInventory && <StatCard loading={loading} label={t("dashboard.expiring")} value={formatNumber(k?.expiring_soon, 0)} tone={(k?.expiring_soon ?? 0) > 0 ? "warning" : "neutral"} icon={<CalendarClock className="size-[18px]" />}
          hint={k && k.expired ? `${k.expired} already expired` : undefined} href="/inventory/expiring" />}
        {finance && <StatCard loading={loading} label={t("dashboard.payables")} value={formatMoney(k?.supplier_payables)} icon={<Wallet className="size-[18px]" />} href="/suppliers" />}
        {finance && <StatCard loading={loading} label={t("dashboard.receivables")} value={formatMoney(k?.customer_receivables)} icon={<HandCoins className="size-[18px]" />} href="/customers" />}
      </section>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <SectionCard className="lg:col-span-2" title={t("dashboard.salesOverview")}
          actions={
            <NativeSelect aria-label="Chart interval" value={granularity} onChange={(e) => setGranularity(e.target.value)} className="h-8 w-32 text-xs">
              <option value="auto">Auto</option><option value="hour">Hourly</option><option value="day">Daily</option><option value="week">Weekly</option><option value="month">Monthly</option><option value="year">Yearly</option>
            </NativeSelect>
          }>
          {loading ? <Skeleton className="h-64 w-full" /> : <SalesChart data={data?.series ?? []} granularity={data?.period.granularity ?? "day"} />}
        </SectionCard>

        <SectionCard title={t("dashboard.categorySales")}>
          {loading ? <Skeleton className="h-64 w-full" /> : <CategoryDonut data={data?.category_sales ?? []} />}
        </SectionCard>

        <SectionCard className="lg:col-span-2" title={t("dashboard.topProducts")}
          actions={
            <NativeSelect aria-label="Number of products" value={topN} onChange={(e) => setTopN(Number(e.target.value))} className="h-8 w-24 text-xs">
              <option value={5}>Top 5</option><option value={10}>Top 10</option><option value={20}>Top 20</option>
            </NativeSelect>
          }>
          {loading ? <Skeleton className="h-64 w-full" /> : <TopProductsChart data={data?.top_products ?? []} />}
        </SectionCard>

        {data?.inventory_status && (
          <SectionCard title={t("dashboard.inventoryStatus")}>
            {loading ? <Skeleton className="h-64 w-full" /> : <InventoryDonut data={data.inventory_status} />}
          </SectionCard>
        )}

        {finance && (
          <SectionCard className="lg:col-span-2" title={t("dashboard.profitTrend")}>
            {loading ? <Skeleton className="h-64 w-full" /> : <ProfitChart data={data?.series ?? []} granularity={data?.period.granularity ?? "day"} />}
          </SectionCard>
        )}

        <SectionCard className={finance ? "" : "lg:col-span-1"} title={t("dashboard.recent")}>
          {loading ? (
            <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : (data?.recent.length ?? 0) === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No transactions yet.</p>
          ) : (
            <ul className="divide-y">
              {data!.recent.map((r) => (
                <li key={`${r.type}-${r.id}`}>
                  <Link href={`${RECENT_HREF[r.type] ?? "/sales"}${r.type === "return" ? "" : `/${r.id}`}`} className="flex items-center justify-between gap-3 py-2.5 text-sm hover:bg-muted/40">
                    <span className="min-w-0">
                      <span className="flex items-center gap-2"><Banknote className="size-3.5 text-muted-foreground" aria-hidden /><span className="truncate font-medium">{r.number}</span></span>
                      <span className="block truncate text-xs text-muted-foreground">{r.party} · {formatDateTime(r.at)}</span>
                    </span>
                    <span className="flex flex-col items-end gap-1">
                      <Money value={r.amount} className="font-medium" signed={r.amount < 0} />
                      <StatusBadge status={r.status} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </>
  )
}
