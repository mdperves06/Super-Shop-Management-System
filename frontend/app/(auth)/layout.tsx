"use client"

import { BarChart3, ScanBarcode, ShieldCheck, Store } from "lucide-react"

import { useShopSettings } from "@/lib/settings"

const POINTS = [
  { icon: ScanBarcode, text: "Fast barcode POS with split payments and credit sales" },
  { icon: BarChart3, text: "Live stock, expiry and profit tracking down to the batch" },
  { icon: ShieldCheck, text: "Role-based access and a full audit trail" },
]

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const settings = useShopSettings()
  const shop = String(settings["shop.name"] ?? "Super Shop")
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-primary p-12 text-primary-foreground lg:flex">
        <div className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-xl bg-white/15"><Store className="size-5" aria-hidden /></span>
          <span className="text-lg font-semibold tracking-tight">{shop}</span>
        </div>
        <div>
          <h2 className="max-w-md text-4xl leading-tight font-semibold tracking-tight">Run your whole super shop from one place.</h2>
          <ul className="mt-8 space-y-4">
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3 text-primary-foreground/90">
                <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-white/15"><Icon className="size-4" aria-hidden /></span>
                <span className="text-[15px]">{text}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-primary-foreground/70">Built for Bangladeshi retail · ৳ BDT · VAT ready · বাংলা</p>
        <div className="pointer-events-none absolute -right-24 -bottom-24 size-96 rounded-full bg-white/10" aria-hidden />
        <div className="pointer-events-none absolute -top-16 -right-10 size-56 rounded-full bg-white/5" aria-hidden />
      </aside>
      <main className="flex items-center justify-center bg-background p-6 sm:p-10">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  )
}
