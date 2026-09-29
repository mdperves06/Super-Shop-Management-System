"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { CheckCircle2, Loader2 } from "lucide-react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Suspense, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Field } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, errorMessage } from "@/lib/api"

const schema = z
  .object({
    password: z.string().min(8, "Use at least 8 characters").refine((v) => /[A-Za-z]/.test(v) && /\d/.test(v), "Include letters and numbers"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match" })

function ResetForm() {
  const token = useSearchParams().get("token") ?? ""
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) })

  async function onSubmit(v: z.infer<typeof schema>) {
    setError(null)
    try {
      await api.post("/auth/reset-password", { token, new_password: v.password })
      setDone(true)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  if (!token) return <p className="text-sm text-destructive" role="alert">This reset link is missing its token. Request a new one.</p>
  if (done) {
    return (
      <div className="text-center">
        <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
        <h1 className="mt-4 text-xl font-semibold">Password updated</h1>
        <Button className="mt-6" render={<Link href="/login" />}>Sign in</Button>
      </div>
    )
  }
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Choose a new password</h1>
      <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-4" noValidate>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <Field label="New password" error={errors.password?.message} hint="At least 8 characters with letters and numbers">{(p) => <Input {...p} type="password" autoComplete="new-password" autoFocus {...register("password")} />}</Field>
        <Field label="Confirm password" error={errors.confirm?.message}>{(p) => <Input {...p} type="password" autoComplete="new-password" {...register("confirm")} />}</Field>
        <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>{isSubmitting && <Loader2 className="size-4 animate-spin" />}Update password</Button>
      </form>
    </div>
  )
}

export default function ResetPasswordPage() {
  return <Suspense><ResetForm /></Suspense>
}
