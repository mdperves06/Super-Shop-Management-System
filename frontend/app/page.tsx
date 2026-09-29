"use client"

import { Loader2 } from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect } from "react"

import { useAuth } from "@/lib/auth"

/** Sends people to the right place: their permission-based landing page, or the login screen. */
export default function Home() {
  const { status, user } = useAuth()
  const router = useRouter()
  useEffect(() => {
    if (status === "authenticated" && user) router.replace(user.landing_path)
    else if (status === "anonymous") router.replace("/login")
  }, [status, user, router])
  return (
    <div className="flex min-h-screen items-center justify-center" role="status">
      <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden />
      <span className="sr-only">Loading…</span>
    </div>
  )
}
