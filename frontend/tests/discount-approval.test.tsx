import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { DiscountApprovalPanel, type useDiscountApproval } from "@/features/pos/discount-approval"
import type { DiscountRequest } from "@/types/api"

type Approval = ReturnType<typeof useDiscountApproval>
const base: DiscountRequest = {
  id: 1, status: "PENDING", discount_percent: 10, discount_amount: 20, reason: "loyal", requested_by: 4, requested_by_name: "Cashier",
  decided_by: null, decided_by_name: null, decided_at: null, decision_note: null, expires_at: "2030-01-01T00:00:00Z", used_sale_id: null,
  created_at: "2030-01-01T00:00:00Z",
}
const make = (request?: Partial<DiscountRequest>, submit = vi.fn()): Approval =>
  ({ request: request ? { ...base, ...request } : undefined, approvedId: request?.status === "APPROVED" ? 1 : undefined, submit, submitting: false }) as Approval

describe("POS discount approval panel", () => {
  it("asks for a reason before a request can be sent", async () => {
    const submit = vi.fn()
    render(<DiscountApprovalPanel approval={make(undefined, submit)} percent={10} limit={5} />)
    const send = screen.getByRole("button", { name: "Request" })
    expect(send).toBeDisabled()
    await userEvent.type(screen.getByLabelText("Reason for discount"), "Regular customer")
    await userEvent.click(send)
    expect(submit).toHaveBeenCalledWith("Regular customer")
  })
  it("shows waiting, approved and rejected states", () => {
    const { rerender } = render(<DiscountApprovalPanel approval={make({ status: "PENDING" })} percent={10} limit={5} />)
    expect(screen.getByText(/Waiting for a manager/)).toBeInTheDocument()
    rerender(<DiscountApprovalPanel approval={make({ status: "APPROVED", decided_by_name: "Boss" })} percent={10} limit={5} />)
    expect(screen.getByText(/Approved by Boss/)).toBeInTheDocument()
    rerender(<DiscountApprovalPanel approval={make({ status: "REJECTED", decision_note: "too high" })} percent={10} limit={5} />)
    expect(screen.getByText(/Rejected: too high/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Request" })).toBeInTheDocument()
  })
})
