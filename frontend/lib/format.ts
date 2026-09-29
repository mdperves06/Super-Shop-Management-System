/**
 * Display formatting only. All arithmetic (totals, tax, discounts, profit) is done by the backend.
 */

export interface FormatConfig {
  currencySymbol: string
  timezone: string
  dateFormat: string // e.g. DD/MM/YYYY
}

let config: FormatConfig = { currencySymbol: "৳", timezone: "Asia/Dhaka", dateFormat: "DD/MM/YYYY" }

export function setFormatConfig(next: Partial<FormatConfig>) {
  config = { ...config, ...next }
}

export function getFormatConfig(): FormatConfig {
  return config
}

const numberFmt = new Intl.NumberFormat("en-BD", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const intFmt = new Intl.NumberFormat("en-BD", { maximumFractionDigits: 0 })
const qtyFmt = new Intl.NumberFormat("en-BD", { maximumFractionDigits: 3 })

export function formatMoney(value: number | null | undefined, opts?: { symbol?: boolean; compact?: boolean }): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—"
  const sym = opts?.symbol === false ? "" : config.currencySymbol
  if (opts?.compact && Math.abs(value) >= 100_000) {
    const f = new Intl.NumberFormat("en-BD", { notation: "compact", maximumFractionDigits: 2 })
    return `${value < 0 ? "-" : ""}${sym}${f.format(Math.abs(value))}`
  }
  const abs = numberFmt.format(Math.abs(value))
  return `${value < 0 ? "-" : ""}${sym}${abs}`
}

export function formatNumber(value: number | null | undefined, digits?: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—"
  if (digits === 0) return intFmt.format(value)
  return qtyFmt.format(value)
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  return `${new Intl.NumberFormat("en-BD", { maximumFractionDigits: 2 }).format(value)}%`
}

function parts(date: Date, opts: Intl.DateTimeFormatOptions) {
  const out: Record<string, string> = {}
  for (const p of new Intl.DateTimeFormat("en-GB", { timeZone: config.timezone, ...opts }).formatToParts(date)) out[p.type] = p.value
  return out
}

export function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null
  if (value instanceof Date) return value
  // date-only strings must not be shifted by the timezone
  const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00Z`) : new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatDate(value: string | Date | null | undefined): string {
  const d = toDate(value)
  if (!d) return "—"
  const dateOnly = typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)
  const p = parts(d, { year: "numeric", month: "2-digit", day: "2-digit", ...(dateOnly ? { timeZone: "UTC" } : {}) })
  const p2 = dateOnly ? parts(d, { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "UTC" }) : p
  return config.dateFormat.replace("DD", p2.day).replace("MM", p2.month).replace("YYYY", p2.year)
}

export function formatTime(value: string | Date | null | undefined): string {
  const d = toDate(value)
  if (!d) return ""
  return new Intl.DateTimeFormat("en-GB", { timeZone: config.timezone, hour: "2-digit", minute: "2-digit", hour12: true }).format(d).toUpperCase()
}

export function formatDateTime(value: string | Date | null | undefined): string {
  const d = toDate(value)
  if (!d) return "—"
  return `${formatDate(d)} ${formatTime(d)}`
}

/** Today's date (YYYY-MM-DD) in the shop timezone. */
export function todayISO(): string {
  const p = parts(new Date(), { year: "numeric", month: "2-digit", day: "2-digit" })
  return `${p.year}-${p.month}-${p.day}`
}

export function addDaysISO(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function humanize(code: string): string {
  return code.replace(/[._]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()).replace(/\s+/g, " ").trim()
}
