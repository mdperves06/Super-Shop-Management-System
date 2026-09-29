"use client"

import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/shared/ui-parts"
import { addDaysISO, todayISO } from "@/lib/format"

export interface DateRange {
  start: string
  end: string
}

export function DateRangeFilter({ value, onChange }: { value: DateRange; onChange: (v: DateRange) => void }) {
  return (
    <div className="flex items-center gap-1.5">
      <Input type="date" aria-label="From date" value={value.start} max={value.end || undefined} onChange={(e) => onChange({ ...value, start: e.target.value })} className="w-36" />
      <span className="text-muted-foreground" aria-hidden>–</span>
      <Input type="date" aria-label="To date" value={value.end} min={value.start || undefined} onChange={(e) => onChange({ ...value, end: e.target.value })} className="w-36" />
    </div>
  )
}

export const PERIODS = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "last_7_days", label: "Last 7 days" },
  { value: "this_month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "this_year", label: "This year" },
  { value: "custom", label: "Custom range" },
] as const

export interface PeriodValue {
  period: string
  start: string
  end: string
}

export function defaultPeriod(period = "today"): PeriodValue {
  const t = todayISO()
  return { period, start: addDaysISO(t, -6), end: t }
}

export function PeriodFilter({ value, onChange }: { value: PeriodValue; onChange: (v: PeriodValue) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <NativeSelect aria-label="Period" value={value.period} onChange={(e) => onChange({ ...value, period: e.target.value })} className="w-40">
        {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
      </NativeSelect>
      {value.period === "custom" && <DateRangeFilter value={{ start: value.start, end: value.end }} onChange={(r) => onChange({ ...value, ...r })} />}
    </div>
  )
}

/** Query params for the period filter; custom ranges are only sent once both dates are chosen. */
export function periodParams(v: PeriodValue) {
  if (v.period === "custom") return v.start && v.end ? { period: "custom", start: v.start, end: v.end } : { period: "this_month" }
  return { period: v.period }
}
