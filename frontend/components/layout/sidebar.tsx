"use client"

import { ChevronDown, Store } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useMemo, useState } from "react"

import { useAuth } from "@/lib/auth"
import { useT } from "@/lib/i18n"
import { isActive, visibleNav } from "@/lib/nav"
import { useShopSettings } from "@/lib/settings"
import { cn } from "@/lib/utils"

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { can } = useAuth()
  const t = useT()
  const pathname = usePathname()
  const items = useMemo(() => visibleNav(can), [can])
  const [open, setOpen] = useState<Record<string, boolean>>({})

  // keep the group containing the current page expanded
  useEffect(() => {
    const current = items.find((i) => i.children?.length && i.children.some((c) => isActive(pathname, c.href)))
    if (current) setOpen((o) => (o[current.href] ? o : { ...o, [current.href]: true })) // eslint-disable-line react-hooks/set-state-in-effect
  }, [pathname, items])

  return (
    <nav aria-label="Main navigation" className="flex flex-col gap-0.5 px-3 py-2">
      {items.map((item) => {
        const Icon = item.icon
        const hasChildren = !!item.children && item.children.length > 1
        const activeChild = item.children?.some((c) => isActive(pathname, c.href, true)) ?? false
        const active = hasChildren ? activeChild : isActive(pathname, item.href, item.href === "/dashboard")
        const base = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring"
        if (!hasChildren) {
          return (
            <Link
              key={item.href}
              href={item.children?.[0]?.href ?? item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(base, active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground")}
            >
              <Icon className="size-[18px] shrink-0" aria-hidden />
              <span className="truncate">{t(item.labelKey)}</span>
            </Link>
          )
        }
        const expanded = !!open[item.href]
        return (
          <div key={item.href}>
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => setOpen((o) => ({ ...o, [item.href]: !o[item.href] }))}
              className={cn(base, active ? "text-sidebar-accent-foreground" : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground")}
            >
              <Icon className="size-[18px] shrink-0" aria-hidden />
              <span className="flex-1 truncate text-left">{t(item.labelKey)}</span>
              <ChevronDown className={cn("size-4 shrink-0 transition-transform", expanded && "rotate-180")} aria-hidden />
            </button>
            {expanded && (
              <ul className="mt-0.5 ml-[21px] flex flex-col gap-0.5 border-l pl-3">
                {item.children!.map((c) => {
                  const childActive = isActive(pathname, c.href, true)
                  return (
                    <li key={c.href}>
                      <Link
                        href={c.href}
                        onClick={onNavigate}
                        aria-current={childActive ? "page" : undefined}
                        className={cn(
                          "block rounded-md px-3 py-1.5 text-[13px] transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          childActive ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
                        )}
                      >
                        {t(c.labelKey)}
                      </Link>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        )
      })}
    </nav>
  )
}

export function Brand() {
  const settings = useShopSettings()
  const name = String(settings["shop.name"] ?? "Super Shop")
  return (
    <Link href="/" className="flex items-center gap-2.5 px-5 py-4 outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <Store className="size-[18px]" aria-hidden />
      </span>
      <span className="truncate text-base font-semibold tracking-tight">{name}</span>
    </Link>
  )
}

export function Sidebar() {
  return (
    <aside className="no-print hidden w-64 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground lg:flex" aria-label="Sidebar">
      <Brand />
      <div className="scroll-thin flex-1 overflow-y-auto pb-6">
        <SidebarNav />
      </div>
    </aside>
  )
}
