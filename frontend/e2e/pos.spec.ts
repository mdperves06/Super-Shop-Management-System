import { expect, test } from "@playwright/test"

import { addToCart, API, apiToken, login, openPos, payExactInCash, stockedProduct } from "./helpers"

test.describe("point of sale", () => {
  test("cashier rings up a cash sale; stock drops and the sale appears in the list", async ({ page, request }) => {
    const item = await stockedProduct(request, { qty: 20, price: 200 })
    await login(page, "cashier@example.com")
    await openPos(page)
    await addToCart(page, item.name)
    await page.getByLabel(`Increase ${item.name}`).click()
    await expect(page.getByLabel(`Quantity of ${item.name}`)).toHaveValue("2")

    await payExactInCash(page)
    await expect(page.getByText(/INV-\d{4}-\d+/).first()).toBeVisible()

    // stock reduced from 20 to 18
    const h = await apiToken(request, "admin@example.com")
    const product = await (await request.get(`${API}/products/${item.id}`, { headers: h })).json()
    expect(product.current_stock).toBe(18)
  })

  test("a discount within the cashier's limit needs no approval", async ({ page, request }) => {
    const item = await stockedProduct(request, { price: 100 })
    await login(page, "cashier@example.com")
    await openPos(page)
    await addToCart(page, item.name)
    await page.getByLabel(`Discount for ${item.name}`).click()
    await page.getByLabel("Discount value").fill("3")
    await expect(page.getByRole("alert").filter({ hasText: /above your/ })).toHaveCount(0)
    await expect(page.getByRole("button", { name: /^Pay/ })).toBeEnabled()
  })
})
