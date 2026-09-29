import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { DataTable } from "@/components/shared/data-table"
import { StatusBadge } from "@/components/shared/ui-parts"
import { estimate } from "@/features/purchasing/purchase-form"
import { settlePayment } from "@/features/pos/payment-dialog"
import { I18nProvider, useT } from "@/lib/i18n"

const auth = vi.hoisted(() => ({ calls: [] as unknown[][], impl: (async () => ({})) as (...a: unknown[]) => Promise<unknown> }))
// a plain function (not vi.fn) so rejected promises are not tracked as unhandled by the spy
const login = (...a: unknown[]) => { auth.calls.push(a); return auth.impl(...a) }
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ login, status: "anonymous", user: null }) }))
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }))

describe("POS payment settlement (mirrors the server)", () => {
  it("cash overpayment produces change", () => {
    const r = settlePayment([{ amount: 1000, isCash: true }], 750)
    expect(r).toMatchObject({ change: 250, applied: 750, due: 0 })
  })
  it("split cash + mobile: mobile is exact, cash covers the rest", () => {
    const r = settlePayment([{ amount: 500, isCash: true }, { amount: 500, isCash: false }], 1000)
    expect(r).toMatchObject({ change: 0, applied: 1000, due: 0 })
  })
  it("short payment leaves an amount on credit", () => {
    expect(settlePayment([{ amount: 300, isCash: true }], 1000)).toMatchObject({ applied: 300, due: 700 })
  })
  it("non-cash cannot be over-tendered", () => {
    expect(settlePayment([{ amount: 1200, isCash: false }], 1000).overOther).toBe(true)
  })
  it("cash tops up the balance after a partial card payment", () => {
    expect(settlePayment([{ amount: 400, isCash: false }, { amount: 1000, isCash: true }], 1000)).toMatchObject({ change: 400, applied: 1000, due: 0 })
  })
})

describe("purchase order estimate", () => {
  it("matches the server example: 100 × 100 − 500 discount + 10% VAT = 10,450", () => {
    const e = estimate([{ quantity: "100", unit_cost: "100", discount_amount: "500", tax_rate: "10" }])
    expect(e).toMatchObject({ subtotal: 10000, discount: 500, tax: 950, total: 10450 })
  })
  it("ignores blank inputs instead of producing NaN", () => {
    expect(estimate([{ quantity: "", unit_cost: "5", discount_amount: "", tax_rate: "" }]).total).toBe(0)
  })
})

describe("DataTable states", () => {
  const cols = [{ id: "n", header: "Name", cell: (r: { n: string }) => r.n }]
  it("shows skeleton rows while loading, not an empty message", () => {
    render(<I18nProvider><DataTable columns={cols} isLoading rowKey={(r) => r.n} /></I18nProvider>)
    expect(screen.queryByText(/no results/i)).not.toBeInTheDocument()
    expect(document.querySelectorAll("[data-slot='skeleton']").length).toBeGreaterThan(0)
  })
  it("shows a helpful empty state with an action", () => {
    render(<I18nProvider><DataTable columns={cols} page={{ items: [], total: 0, page: 1, page_size: 20, pages: 1 }} rowKey={(r) => r.n} empty={{ title: "No products found.", action: <button>+ Add Product</button> }} /></I18nProvider>)
    expect(screen.getByText("No products found.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "+ Add Product" })).toBeInTheDocument()
  })
  it("shows a retryable error instead of a broken table", async () => {
    const retry = vi.fn()
    render(<I18nProvider><DataTable columns={cols} error={new Error("Cannot reach the server")} onRetry={retry} rowKey={(r) => r.n} /></I18nProvider>)
    expect(screen.getByRole("alert")).toHaveTextContent("Cannot reach the server")
    await userEvent.click(screen.getByRole("button", { name: /try again/i }))
    expect(retry).toHaveBeenCalled()
  })
  it("paginates through the server page info", async () => {
    const onPage = vi.fn()
    render(<I18nProvider><DataTable columns={cols} page={{ items: [{ n: "Milk" }], total: 45, page: 2, page_size: 20, pages: 3 }} onPageChange={onPage} rowKey={(r) => r.n} /></I18nProvider>)
    expect(screen.getByText("Milk")).toBeInTheDocument()
    expect(screen.getByText("Showing 21–40 of 45")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /next/i }))
    expect(onPage).toHaveBeenCalledWith(3)
  })
})

describe("StatusBadge", () => {
  it("maps business statuses to readable labels", () => {
    render(<><StatusBadge status="PARTIALLY_RECEIVED" /><StatusBadge status="out" /></>)
    expect(screen.getByText("Partially Received")).toBeInTheDocument()
    expect(screen.getByText("Out of stock")).toBeInTheDocument()
  })
})

describe("i18n", () => {
  function Probe() {
    const t = useT()
    return <p>{t("nav.dashboard")} | {t("common.rowsOf", { from: 1, to: 2, total: 9 })} | {t("missing.key")}</p>
  }
  it("translates, interpolates and falls back to the key", () => {
    render(<I18nProvider><Probe /></I18nProvider>)
    expect(screen.getByText("Dashboard | Showing 1–2 of 9 | missing.key")).toBeInTheDocument()
  })
})

describe("login form", () => {
  beforeEach(() => { auth.calls.length = 0 })

  it("validates before calling the server, then signs in", async () => {
    const { default: LoginPage } = await import("@/app/(auth)/login/page")
    auth.impl = async () => ({ landing_path: "/dashboard", must_change_password: false })
    const qc = new QueryClient()
    render(<QueryClientProvider client={qc}><I18nProvider><LoginPage /></I18nProvider></QueryClientProvider>)
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }))
    expect(await screen.findByText("Enter your email")).toBeInTheDocument()
    expect(auth.calls).toHaveLength(0)

    await userEvent.type(screen.getByLabelText(/email/i), "cashier@example.com")
    await userEvent.type(screen.getByLabelText(/^password/i), "Demo@12345")
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }))
    await waitFor(() => expect(auth.calls[0]).toEqual(["cashier@example.com", "Demo@12345", ""])) // otp left blank
  })

  it("shows the server’s message for a failed login", async () => {
    const { ApiError } = await import("@/lib/api")
    const { default: LoginPage } = await import("@/app/(auth)/login/page")
    auth.impl = async () => { throw new ApiError(401, "invalid_credentials", "Invalid email or password") }
    render(<QueryClientProvider client={new QueryClient()}><I18nProvider><LoginPage /></I18nProvider></QueryClientProvider>)
    await userEvent.type(screen.getByLabelText(/email/i), "a@b.co")
    await userEvent.type(screen.getByLabelText(/^password/i), "wrong")
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password")
  })
})
