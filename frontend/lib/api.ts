/**
 * Thin fetch client for the FastAPI backend.
 * - attaches the bearer token
 * - transparently refreshes an expired access token once (single-flight)
 * - normalises errors into ApiError with a user-friendly message
 */

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "")
const PREFIX = "/api/v1"

const ACCESS_KEY = "ssm.access"
const REFRESH_KEY = "ssm.refresh"

export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

export const tokenStore = {
  get access(): string | null {
    if (typeof window === "undefined") return null
    try { return localStorage.getItem(ACCESS_KEY) } catch { return null }
  },
  get refresh(): string | null {
    if (typeof window === "undefined") return null
    try { return localStorage.getItem(REFRESH_KEY) } catch { return null }
  },
  set(access: string, refresh: string) {
    try {
      localStorage.setItem(ACCESS_KEY, access)
      localStorage.setItem(REFRESH_KEY, refresh)
    } catch { /* storage unavailable: session lasts until reload */ }
  },
  clear() {
    try {
      localStorage.removeItem(ACCESS_KEY)
      localStorage.removeItem(REFRESH_KEY)
    } catch { /* ignore */ }
  },
}

type Query = Record<string, string | number | boolean | null | undefined>

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${API_URL}${path.startsWith("/media") ? "" : PREFIX}${path}`)
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v))
    }
  }
  return url.toString()
}

let refreshing: Promise<boolean> | null = null

async function refreshTokens(): Promise<boolean> {
  if (refreshing) return refreshing
  const refresh = tokenStore.refresh
  if (!refresh) return false
  refreshing = (async () => {
    try {
      const res = await fetch(buildUrl("/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      })
      if (!res.ok) return false
      const data = await res.json()
      tokenStore.set(data.access_token, data.refresh_token)
      return true
    } catch {
      return false
    } finally {
      setTimeout(() => { refreshing = null }, 0)
    }
  })()
  return refreshing
}

function friendly(status: number, code: string, message: string): string {
  if (status === 0) return "Cannot reach the server. Check your connection and try again."
  if (status === 403) return message || "You do not have permission to do that."
  if (status === 429) return "Too many requests. Please wait a moment."
  if (status >= 500) return "Something went wrong on the server. Please try again."
  return message || `Request failed (${code})`
}

async function parseError(res: Response): Promise<ApiError> {
  let code = "http_error"
  let message = ""
  let details: unknown
  try {
    const body = await res.json()
    if (body?.error) {
      code = body.error.code ?? code
      message = body.error.message ?? ""
      details = body.error.details
    }
  } catch { /* non-JSON body */ }
  return new ApiError(res.status, code, friendly(res.status, code, message), details)
}

interface RequestOptions {
  method?: string
  query?: Query
  body?: unknown
  form?: FormData
  auth?: boolean
  raw?: boolean
}

async function send(path: string, opts: RequestOptions, retry = true): Promise<Response> {
  const headers: Record<string, string> = {}
  if (opts.auth !== false && tokenStore.access) headers.Authorization = `Bearer ${tokenStore.access}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json"
    body = JSON.stringify(opts.body)
  }
  let res: Response
  try {
    res = await fetch(buildUrl(path, opts.query), { method: opts.method ?? "GET", headers, body })
  } catch {
    throw new ApiError(0, "network_error", friendly(0, "network_error", ""))
  }
  if (res.status === 401 && opts.auth !== false && retry) {
    const clone = res.clone()
    let code = ""
    try { code = (await clone.json())?.error?.code } catch { /* ignore */ }
    if (["token_expired", "token_invalid", "session_expired", "not_authenticated"].includes(code) && tokenStore.refresh) {
      if (await refreshTokens()) return send(path, opts, false)
    }
    if (code && code !== "invalid_credentials") {
      tokenStore.clear()
      if (typeof window !== "undefined") window.dispatchEvent(new Event("ssm:logout"))
    }
  }
  if (!res.ok) throw await parseError(res)
  return res
}

async function json<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await send(path, opts)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string, query?: Query) => json<T>(path, { query }),
  post: <T>(path: string, body?: unknown, query?: Query) => json<T>(path, { method: "POST", body: body ?? {}, query }),
  put: <T>(path: string, body?: unknown) => json<T>(path, { method: "PUT", body: body ?? {} }),
  patch: <T>(path: string, body?: unknown) => json<T>(path, { method: "PATCH", body: body ?? {} }),
  delete: <T>(path: string) => json<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => json<T>(path, { method: "POST", form }),
  async blob(path: string, query?: Query): Promise<Blob> {
    const res = await send(path, { query })
    return res.blob()
  },
}

/** Fetch an authenticated file and open it in a new tab (PDFs). */
export async function openFile(path: string, query?: Query) {
  const blob = await api.blob(path, query)
  const url = URL.createObjectURL(blob)
  window.open(url, "_blank", "noopener")
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** Fetch an authenticated file and save it (CSV / XLSX / backups). */
export async function downloadFile(path: string, filename: string, query?: Query) {
  const blob = await api.blob(path, query)
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null
  return `${API_URL}/media/${path}`
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error) return e.message
  return "Something went wrong"
}
