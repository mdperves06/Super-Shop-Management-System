import { expect, type Page } from "@playwright/test"

export const PASSWORD = "Demo@12345" // public seed password (backend/seed.py), development databases only

export async function login(page: Page, email: string, password = PASSWORD) {
  await page.goto("/login")
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password", { exact: true }).fill(password)
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

export async function logout(page: Page) {
  await page.getByRole("button", { name: /account|profile|user menu/i }).first().click()
  await page.getByRole("menuitem", { name: "Sign out" }).click()
  await expect(page).toHaveURL(/\/login/)
}

// ---- API helpers: set up prerequisite data quickly so each spec exercises only the flow it is about -------------

import type { APIRequestContext } from "@playwright/test"

export const API = "http://localhost:8100/api/v1"
let counter = Date.now() % 1_000_000

export async function apiToken(request: APIRequestContext, email: string): Promise<Record<string, string>> {
  const r = await request.post(`${API}/auth/login`, { data: { email, password: PASSWORD }, headers: { "X-Token-Delivery": "body" } })
  expect(r.ok()).toBeTruthy()
  return { Authorization: `Bearer ${(await r.json()).access_token}` }
}

/** A product with `qty` units received through a real approved + received purchase order. */
export async function stockedProduct(request: APIRequestContext, opts: { qty?: number; price?: number; cost?: number } = {}) {
  const { qty = 50, price = 200, cost = 100 } = opts
  const h = await apiToken(request, "admin@example.com")
  const n = ++counter
  const units = await (await request.get(`${API}/units`, { headers: h })).json()
  const product = await (await request.post(`${API}/products`, {
    headers: h,
    data: { sku: `E2E-${n}`, name: `E2E Item ${n}`, unit_id: units[0].id, purchase_price: 0, selling_price: price, reorder_level: 1 },
  })).json()
  const supplier = await (await request.post(`${API}/suppliers`, { headers: h, data: { name: `E2E Supplier ${n}`, phone: `0170${n}` } })).json()
  const po = await (await request.post(`${API}/purchases`, {
    headers: h, data: { supplier_id: supplier.id, items: [{ product_id: product.id, quantity: qty, unit_cost: cost }] },
  })).json()
  expect((await request.post(`${API}/purchases/${po.id}/approve`, { headers: h })).ok()).toBeTruthy()
  const recv = await request.post(`${API}/purchases/${po.id}/receive`, { headers: h, data: { items: [{ item_id: po.items[0].id, quantity: qty }] } })
  expect(recv.ok()).toBeTruthy()
  return { id: product.id as number, name: product.name as string, sku: product.sku as string }
}

/** Opens the POS and, if the cashier has no open cash-register session, opens one. */
export async function openPos(page: Page) {
  await page.goto("/pos")
  const open = page.getByRole("button", { name: "Open register" })
  const scan = page.getByLabel("Scan barcode or search product")
  await expect(open.or(scan)).toBeVisible()
  if (await open.isVisible()) {
    await page.getByLabel("Opening cash").fill("5000")
    await open.click()
  }
  await expect(scan).toBeVisible()
}

export async function addToCart(page: Page, productName: string) {
  await page.getByLabel("Scan barcode or search product").fill(productName)
  await page.getByRole("button", { name: new RegExp(`^Add ${productName}`) }).click()
  await expect(page.getByLabel(`Quantity of ${productName}`)).toHaveValue("1")
}

export async function payExactInCash(page: Page) {
  await page.getByRole("button", { name: /^Pay/ }).click()
  await page.getByRole("button", { name: "Exact" }).click()
  await page.getByRole("button", { name: "Complete sale" }).click()
}
