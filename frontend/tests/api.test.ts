import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, api, tokenStore } from "@/lib/api"

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })

beforeEach(async () => {
  await new Promise((r) => setTimeout(r, 5)) // let the client's single-flight refresh guard reset between tests
  vi.restoreAllMocks()
  tokenStore.set("old-access", "old-refresh")
})

describe("api client", () => {
  it("sends the bearer token and query string", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { ok: true }))
    await api.get("/products", { page: 2, search: "milk", empty: "", nothing: undefined })
    const [url, init] = spy.mock.calls[0]
    expect(String(url)).toContain("/api/v1/products?page=2&search=milk")
    expect(String(url)).not.toContain("empty")
    expect((init!.headers as Record<string, string>).Authorization).toBe("Bearer old-access")
  })

  it("maps backend error envelopes to ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(409, { error: { code: "insufficient_stock", message: "Only 3 left", details: { available: 3 } } }))
    await expect(api.post("/sales", {})).rejects.toMatchObject({ status: 409, code: "insufficient_stock", message: "Only 3 left", details: { available: 3 } })
  })

  it("never shows raw server errors to users", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(500, { error: { code: "internal_error", message: "Traceback ... psycopg" } }))
    const err = (await api.get("/x").catch((e: unknown) => e)) as ApiError
    expect(err.message).toBe("Something went wrong on the server. Please try again.")
  })

  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"))
    await expect(api.get("/x")).rejects.toMatchObject({ status: 0, code: "network_error" })
  })

  it("refreshes an expired access token once and retries the request", async () => {
    const spy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json(401, { error: { code: "token_expired", message: "expired" } }))
      .mockResolvedValueOnce(json(200, { access_token: "new-access", refresh_token: "new-refresh" }))
      .mockResolvedValueOnce(json(200, { hello: "world" }))
    const out = await api.get<{ hello: string }>("/auth/me")
    expect(out.hello).toBe("world")
    expect(spy).toHaveBeenCalledTimes(3)
    expect(tokenStore.access).toBe("new-access")
    expect((spy.mock.calls[2][1]!.headers as Record<string, string>).Authorization).toBe("Bearer new-access")
  })

  it("signs the user out when the refresh token is rejected", async () => {
    const onLogout = vi.fn()
    window.addEventListener("ssm:logout", onLogout)
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json(401, { error: { code: "token_expired", message: "expired" } }))
      .mockResolvedValueOnce(json(401, { error: { code: "session_expired", message: "gone" } }))
    await expect(api.get("/auth/me")).rejects.toBeInstanceOf(ApiError)
    expect(tokenStore.access).toBeNull()
    expect(onLogout).toHaveBeenCalled()
    window.removeEventListener("ssm:logout", onLogout)
  })

  it("does not treat a wrong password as an expired session", async () => {
    const onLogout = vi.fn()
    window.addEventListener("ssm:logout", onLogout)
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(401, { error: { code: "invalid_credentials", message: "Invalid email or password" } }))
    await expect(api.post("/auth/login", { email: "a@b.co", password: "x" })).rejects.toMatchObject({ code: "invalid_credentials" })
    expect(onLogout).not.toHaveBeenCalled()
    window.removeEventListener("ssm:logout", onLogout)
  })
})
