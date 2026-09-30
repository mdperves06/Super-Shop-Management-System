import { expect, test } from "@playwright/test"

import { login, PASSWORD } from "./helpers"

test.describe("authentication", () => {
  test("rejects a wrong password and accepts the right one, landing on the dashboard", async ({ page }) => {
    await page.goto("/login")
    await page.getByLabel("Email").fill("admin@example.com")
    await page.getByLabel("Password", { exact: true }).fill("Wrong-pass-1")
    await page.getByRole("button", { name: "Sign in", exact: true }).click()
    await expect(page.getByRole("alert").filter({ hasText: /./ })).toContainText(/invalid/i)
    await expect(page).toHaveURL(/\/login/)

    await login(page, "admin@example.com")
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.getByRole("heading", { name: /dashboard/i }).first()).toBeVisible()
  })

  test("session survives a reload via the HttpOnly refresh cookie, and the token is not readable by scripts", async ({ page, context }) => {
    await login(page, "manager@example.com")
    await page.reload()
    await expect(page).toHaveURL(/\/dashboard/)
    const cookies = await context.cookies()
    const refresh = cookies.find((c) => c.name === "ssm_refresh")
    expect(refresh?.httpOnly).toBe(true)
    expect(await page.evaluate(() => document.cookie)).not.toContain("ssm_refresh")
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage }))).not.toMatch(/refresh/i)
  })

  test("protected pages redirect anonymous visitors to the login page", async ({ page }) => {
    await page.goto("/products")
    await expect(page).toHaveURL(/\/login/)
  })

  test("password reset: request a link, use it once, sign in with the new password", async ({ page }) => {
    const email = "staff@example.com"
    const fresh = "Fresh-Pass-4567"
    await page.goto("/forgot-password")
    await page.getByLabel("Email").fill(email)
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith("/auth/forgot-password")),
      page.getByRole("button", { name: "Send reset link" }).click(),
    ])
    await expect(page.getByText("Check your email")).toBeVisible()
    const token = (await response.json()).dev_token as string // only present outside production
    expect(token).toBeTruthy()

    await page.goto(`/reset-password?token=${token}`)
    await page.getByLabel("New password").fill(fresh)
    await page.getByLabel("Confirm password").fill(fresh)
    await page.getByRole("button", { name: "Update password" }).click()
    await expect(page.getByText("Password updated")).toBeVisible()

    // the link is single use
    await page.goto(`/reset-password?token=${token}`)
    await page.getByLabel("New password").fill("Another-Pass-789")
    await page.getByLabel("Confirm password").fill("Another-Pass-789")
    await page.getByRole("button", { name: "Update password" }).click()
    await expect(page.getByRole("alert").filter({ hasText: /./ })).toContainText(/invalid or has expired/i)

    await login(page, email, fresh)
    await expect(page).not.toHaveURL(/\/login/)

    // put the seed password back so the other specs keep working
    await page.request.post("http://localhost:8100/api/v1/auth/forgot-password", { data: { email } }).then(async (r) => {
      const t = (await r.json()).dev_token
      await page.request.post("http://localhost:8100/api/v1/auth/reset-password", { data: { token: t, new_password: PASSWORD } })
    })
  })
})
