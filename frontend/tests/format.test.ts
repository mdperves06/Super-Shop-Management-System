import { describe, expect, it } from "vitest"

import { addDaysISO, formatDate, formatDateTime, formatMoney, formatNumber, formatPercent, humanize, setFormatConfig } from "@/lib/format"

describe("formatMoney", () => {
  it("uses the taka sign, two decimals and South-Asian digit grouping", () => {
    expect(formatMoney(1234567.5)).toBe("৳12,34,567.50")
    expect(formatMoney(0)).toBe("৳0.00")
  })
  it("shows negatives with the sign in front", () => expect(formatMoney(-500)).toBe("-৳500.00"))
  it("can omit the symbol and handles missing values", () => {
    expect(formatMoney(99.5, { symbol: false })).toBe("99.50")
    expect(formatMoney(null)).toBe("—")
    expect(formatMoney(undefined)).toBe("—")
    expect(formatMoney(Number.NaN)).toBe("—")
  })
  it("compacts large chart values", () => expect(formatMoney(2_500_000, { compact: true })).toMatch(/৳.*(25|2\.5)/))
})

describe("numbers", () => {
  it("keeps up to three decimals for quantities", () => expect(formatNumber(1.2345)).toBe("1.235"))
  it("rounds integers", () => expect(formatNumber(7.6, 0)).toBe("8"))
  it("formats percentages", () => expect(formatPercent(12.5)).toBe("12.5%"))
})

describe("dates (Asia/Dhaka)", () => {
  it("date-only strings are not shifted by the timezone", () => expect(formatDate("2026-09-30")).toBe("30/09/2026"))
  it("converts UTC timestamps to shop time", () => {
    // 20:30 UTC on 30 Sep is 02:30 on 1 Oct in Dhaka (UTC+6)
    expect(formatDate("2026-09-30T20:30:00Z")).toBe("01/10/2026")
    expect(formatDateTime("2026-09-30T20:30:00Z")).toBe("01/10/2026 02:30 AM")
  })
  it("respects the configured date format", () => {
    setFormatConfig({ dateFormat: "YYYY-MM-DD" })
    expect(formatDate("2026-09-30")).toBe("2026-09-30")
    setFormatConfig({ dateFormat: "DD/MM/YYYY" })
  })
  it("adds days across month boundaries", () => expect(addDaysISO("2026-09-30", 1)).toBe("2026-10-01"))
  it("handles empty input", () => expect(formatDate(null)).toBe("—"))
})

describe("humanize", () => {
  it("turns codes into labels", () => expect(humanize("sale.void")).toBe("Sale Void"))
})
