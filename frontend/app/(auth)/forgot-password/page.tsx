"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { CheckCircle2, Loader2 } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Field } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, errorMessage } from "@/lib/api"

const schema = z.object({ email: z.string().min(1, "Enter your email").email("Enter a valid email address") })

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) })

  async function onSubmit(values: z.infer<typeof schema>) {
    setError(null)
    try {
      await api.post("/auth/forgot-password", values)
      setSent(true)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  if (sent) {
    return (
      <div className="text-center">
        <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
        <h1 className="mt-4 text-xl font-semibold">Check your email</h1>
        <p className="mt-2 text-sm text-muted-foreground">If an account exists for that address, we’ve sent a link to reset the password. It expires in one hour.</p>
        <Button variant="outline" className="mt-6" render={<Link href="/login" />}>Back to sign in</Button>
      </div>
    )
  }
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Reset your password</h1>
      <p className="mt-1 text-sm text-muted-foreground">Enter your account email and we’ll send you a reset link.</p>
      <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-4" noValidate>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <Field label="Email" error={errors.email?.message}>{(p) => <Input {...p} type="email" autoComplete="email" autoFocus {...register("email")} />}</Field>
        <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>{isSubmitting && <Loader2 className="size-4 animate-spin" />}Send reset link</Button>
        <div className="text-center"><Link href="/login" className="text-sm text-primary hover:underline">Back to sign in</Link></div>
      </form>
    </div>
  )
}
