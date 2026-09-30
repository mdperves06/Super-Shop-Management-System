import { expect, test } from "@playwright/test"

import { addToCart, login, openPos, payExactInCash, stockedProduct } from "./helpers"

test("cashier requests a discount above the limit; a manager approves it; the sale then goes through once", async ({ browser, request }) => {
  const item = await stockedProduct(request, { qty: 10, price: 100 })
  const cashierCtx = await browser.newContext()
  const managerCtx = await browser.newContext()
  const cashier = await cashierCtx.newPage()
  const manager = await managerCtx.newPage()

  await login(cashier, "cashier@example.com")
  await openPos(cashier)
  await addToCart(cashier, item.name)
  await cashier.getByLabel(`Discount for ${item.name}`).click()
  await cashier.getByLabel("Discount value").fill("20")

  // over the limit: payment is blocked until a manager approves
  await expect(cashier.getByText(/above your \d+(\.\d+)?% limit/)).toBeVisible()
  await expect(cashier.getByRole("button", { name: /^Pay/ })).toBeDisabled()
  await cashier.getByLabel("Reason for discount").fill("Damaged packaging")
  await cashier.getByRole("button", { name: "Request", exact: true }).click()
  await expect(cashier.getByText(/Waiting for a manager/)).toBeVisible()

  // the manager sees it in the queue and approves
  await login(manager, "manager@example.com")
  await manager.goto("/sales/discount-requests")
  const row = manager.getByRole("row").filter({ hasText: "Damaged packaging" })
  await expect(row).toBeVisible()
  await row.getByRole("button", { name: "Approve" }).click()
  await manager.getByRole("dialog").getByRole("button", { name: "Approve" }).click()
  await expect(manager.getByRole("row").filter({ hasText: "Damaged packaging" })).toHaveCount(0) // leaves the pending queue

  // the POS notices within its polling interval and lets the cashier take payment
  await expect(cashier.getByText(/Approved by/)).toBeVisible({ timeout: 15_000 })
  await expect(cashier.getByRole("button", { name: /^Pay/ })).toBeEnabled()
  await payExactInCash(cashier)
  await expect(cashier.getByText(/INV-\d{4}-\d+/).first()).toBeVisible()

  // approvals are single use: the queue now lists it as used
  await manager.goto("/sales/discount-requests")
  await manager.getByLabel("Status filter").selectOption("USED")
  await expect(manager.getByRole("row").filter({ hasText: "Damaged packaging" })).toBeVisible()

  await cashierCtx.close()
  await managerCtx.close()
})

test("a manager can reject a request with a reason and the cashier is told", async ({ browser, request }) => {
  const item = await stockedProduct(request, { qty: 10, price: 100 })
  const cashierCtx = await browser.newContext()
  const managerCtx = await browser.newContext()
  const cashier = await cashierCtx.newPage()
  const manager = await managerCtx.newPage()

  await login(cashier, "cashier@example.com")
  await openPos(cashier)
  await addToCart(cashier, item.name)
  await cashier.getByLabel(`Discount for ${item.name}`).click()
  await cashier.getByLabel("Discount value").fill("30")
  await cashier.getByLabel("Reason for discount").fill("Friend of owner")
  await cashier.getByRole("button", { name: "Request", exact: true }).click()

  await login(manager, "manager@example.com")
  await manager.goto("/sales/discount-requests")
  const row = manager.getByRole("row").filter({ hasText: "Friend of owner" })
  await row.getByRole("button", { name: "Reject" }).click()
  const dialog = manager.getByRole("dialog")
  await expect(dialog.getByRole("button", { name: "Reject" })).toBeDisabled() // a reason is mandatory
  await dialog.getByLabel(/Reason for rejecting/).fill("Too generous")
  await dialog.getByRole("button", { name: "Reject" }).click()

  await expect(cashier.getByText(/Rejected: Too generous/)).toBeVisible({ timeout: 15_000 })
  await expect(cashier.getByRole("button", { name: /^Pay/ })).toBeDisabled()
  await cashierCtx.close()
  await managerCtx.close()
})
