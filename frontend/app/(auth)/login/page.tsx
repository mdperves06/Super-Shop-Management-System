"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Eye, EyeOff, Loader2 } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Field } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { useT } from "@/lib/i18n"

const schema = z.object({
  email: z.string().min(1, "Enter your email").email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
  otp: z.string().optional(),
})
type Values = z.infer<typeof schema>

const DEMO = [
  ["admin@example.com", "Owner"],
  ["manager@example.com", "Manager"],
  ["cashier@example.com", "Cashier"],
  ["inventory@example.com", "Inventory"],
  ["accountant@example.com", "Accountant"],
]

export default function LoginPage() {
  const { login, status, user } = useAuth()
  const router = useRouter()
  const t = useT()
  const [show, setShow] = useState(false)
  const [needOtp, setNeedOtp] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const { register, handleSubmit, setValue, formState: { errors, isSubmitting } } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "", otp: "" } })
  const showDemo = process.env.NEXT_PUBLIC_SHOW_DEMO_LOGINS === "true"

  useEffect(() => {
    if (status === "authenticated" && user) router.replace(user.landing_path)
  }, [status, user, router])

  async function onSubmit(values: Values) {
    setFormError(null)
    try {
      const me = await login(values.email, values.password, values.otp)
      router.replace(me.must_change_password ? "/profile?change-password=1" : me.landing_path)
    } catch (e) {
      if (e instanceof ApiError && e.code === "otp_required") {
        setNeedOtp(true)
        setFormError("Enter the 6-digit code from your authenticator app.")
      } else if (e instanceof ApiError) {
        setFormError(e.message)
      } else {
        setFormError("Something went wrong. Please try again.")
      }
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">{t("auth.title")}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{t("auth.subtitle")}</p>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-4" noValidate>
        {formError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{formError}</div>}
        <Field label={t("auth.email")} error={errors.email?.message}>
          {(p) => <Input {...p} type="email" autoComplete="username" autoFocus placeholder="you@shop.com" {...register("email")} />}
        </Field>
        <Field label={t("auth.password")} error={errors.password?.message}>
          {(p) => (
            <div className="relative">
              <Input {...p} type={show ? "text" : "password"} autoComplete="current-password" className="pr-10" {...register("password")} />
              <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground">
                {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          )}
        </Field>
        {needOtp && (
          <Field label={t("auth.otp")} error={errors.otp?.message}>
            {(p) => <Input {...p} inputMode="numeric" autoComplete="one-time-code" maxLength={8} autoFocus placeholder="123456" {...register("otp")} />}
          </Field>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="size-4 animate-spin" aria-hidden />}
          {t("action.signin")}
        </Button>
        <div className="text-center">
          <Link href="/forgot-password" className="text-sm text-primary hover:underline">{t("auth.forgot")}</Link>
        </div>
      </form>

      {showDemo && (
        <div className="mt-8 rounded-lg border bg-muted/40 p-3">
          <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{t("auth.demo")} <span className="normal-case">(dev only · password Demo@12345)</span></p>
          <div className="flex flex-wrap gap-1.5">
            {DEMO.map(([email, label]) => (
              <button key={email} type="button" onClick={() => { setValue("email", email); setValue("password", "Demo@12345") }} className="rounded-md border bg-background px-2 py-1 text-xs hover:bg-accent">
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
