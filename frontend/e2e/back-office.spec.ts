import { expect, test, type Page } from "@playwright/test"

import { login } from "./helpers"

async function pick(page: Page, placeholder: RegExp | string, search: string) {
  await page.getByRole("combobox").filter({ hasText: placeholder }).click()
  await page.getByLabel("Search options").fill(search)
  await (search ? page.getByRole("option").filter({ hasText: search }) : page.getByRole("option")).first().click()
}

test.describe("catalogue, purchasing, inventory and reports", () => {
  const stamp = Date.now() % 100000
  const name = `E2E Widget ${stamp}`
  const sku = `WID-${stamp}`

  test("admin creates a product, buys stock for it, and sees it in inventory", async ({ page }) => {
    await login(page, "admin@example.com")

    // product management
    await page.goto("/products/new")
    await page.getByLabel("Product name").fill(name)
    await page.getByLabel("SKU").fill(sku)
    await page.getByLabel("Unit").selectOption({ index: 1 })
    await page.getByLabel("Purchase price (cost)").fill("80")
    await page.getByLabel("Selling price").fill("120")
    await page.getByRole("button", { name: "Create product" }).click()
    await expect(page).toHaveURL(/\/products\/\d+/)
    await expect(page.getByText(name).first()).toBeVisible()

    // purchasing: draft -> approve -> receive
    await page.goto("/purchases/new")
    await pick(page, /Choose supplier/, "")
    await pick(page, /Add a product/, name)
    await page.getByLabel(`quantity for ${name}`).fill("15")
    await page.getByLabel(`unit cost for ${name}`).fill("80")
    await page.getByRole("button", { name: "Save & submit" }).click()
    await expect(page).toHaveURL(/\/purchases\/\d+/)
    await page.getByRole("button", { name: "Approve" }).click()
    await page.getByRole("button", { name: "Receive stock" }).click()
    await page.getByRole("button", { name: "Confirm receipt" }).click()
    await expect(page.getByText(/RECEIVED|Received/).first()).toBeVisible()

    // inventory shows the 15 units
    await page.goto("/inventory")
    await page.getByPlaceholder(/search/i).first().fill(sku)
    const row = page.getByRole("row").filter({ hasText: sku })
    await expect(row).toBeVisible()
    await expect(row).toContainText("15")
  })

  test("sales report loads with data and exports to CSV", async ({ page }) => {
    await login(page, "admin@example.com")
    await page.goto("/reports/sales")
    await expect(page.getByRole("heading", { name: /sales/i }).first()).toBeVisible()
    await expect(page.getByRole("table")).toBeVisible()
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "CSV" }).click()])
    expect(download.suggestedFilename()).toMatch(/\.csv$/)
  })
})
