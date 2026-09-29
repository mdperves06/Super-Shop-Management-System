"use client"

import { Bell, Languages, LogOut, Menu, Moon, Search, Sun, User as UserIcon } from "lucide-react"
import { useTheme } from "next-themes"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { Brand, SidebarNav } from "@/components/layout/sidebar"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet"
import { useDebounce } from "@/hooks/use-debounce"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { useI18n } from "@/lib/i18n"
import { cn } from "@/lib/utils"

type SearchResults = Record<string, { id: number; title: string; subtitle: string; href: string }[]>

function GlobalSearch() {
  const [q, setQ] = useState("")
  const [open, setOpen] = useState(false)
  const debounced = useDebounce(q.trim(), 250)
  const router = useRouter()
  const box = useRef<HTMLDivElement>(null)
  const { data, isFetching } = useQuery({
    queryKey: ["global-search", debounced],
    queryFn: () => api.get<SearchResults>("/search", { q: debounced }),
    enabled: debounced.length >= 2,
    staleTime: 10_000,
  })

  useEffect(() => {
    const onClick = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); box.current?.querySelector("input")?.focus() }
    }
    document.addEventListener("mousedown", onClick)
    document.addEventListener("keydown", onKey)
    return () => { document.removeEventListener("mousedown", onClick); document.removeEventListener("keydown", onKey) }
  }, [])

  const groups = data ? Object.entries(data) : []
  return (
    <div ref={box} className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <Input
        value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Escape") setOpen(false) }}
        placeholder="Search products, customers, invoices…  (Ctrl+K)"
        aria-label="Global search"
        className="pl-9"
      />
      {open && debounced.length >= 2 && (
        <div className="absolute top-11 z-50 max-h-96 w-full overflow-y-auto rounded-lg border bg-popover p-1 shadow-lg" role="listbox">
          {isFetching && !data && <p className="px-3 py-2 text-sm text-muted-foreground">Searching…</p>}
          {data && groups.length === 0 && <p className="px-3 py-3 text-sm text-muted-foreground">No matches for “{debounced}”.</p>}
          {groups.map(([group, rows]) => (
            <div key={group} className="py-1">
              <p className="px-3 py-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">{group}</p>
              {rows.map((r) => (
                <button
                  key={`${group}-${r.id}`}
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() => { setOpen(false); setQ(""); router.push(r.href) }}
                  className="flex w-full flex-col rounded-md px-3 py-1.5 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
                >
                  <span className="font-medium">{r.title}</span>
                  <span className="text-xs text-muted-foreground">{r.subtitle}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function NotificationBell() {
  const { can } = useAuth()
  const { data } = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: () => api.get<{ count: number }>("/notifications/unread-count"),
    enabled: can("notification.read"),
    refetchInterval: 60_000,
  })
  if (!can("notification.read")) return null
  const count = data?.count ?? 0
  return (
    <Button variant="ghost" size="icon" aria-label={count ? `${count} unread notifications` : "Notifications"} render={<Link href="/notifications" />} className="relative">
      <Bell className="size-[18px]" />
      {count > 0 && (
        <span className="absolute top-1 right-1 flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] leading-4 font-semibold text-white">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Button>
  )
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), []) // eslint-disable-line react-hooks/set-state-in-effect
  const dark = mounted && resolvedTheme === "dark"
  return (
    <Button variant="ghost" size="icon" aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} onClick={() => setTheme(dark ? "light" : "dark")}>
      {dark ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
    </Button>
  )
}

function LanguageToggle() {
  const { locale, setLocale } = useI18n()
  return (
    <Button variant="ghost" size="sm" aria-label="Change language" onClick={() => setLocale(locale === "en" ? "bn" : "en")} className="gap-1.5">
      <Languages className="size-4" />
      <span className="text-xs font-semibold">{locale === "en" ? "বাং" : "EN"}</span>
    </Button>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const initials = (user?.full_name ?? "?").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" className="h-10 gap-2 px-1.5" aria-label="Account menu" />}>
        <Avatar className="size-8"><AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">{initials}</AvatarFallback></Avatar>
        <span className="hidden text-left leading-tight md:block">
          <span className="block max-w-32 truncate text-sm font-medium">{user?.full_name}</span>
          <span className="block max-w-32 truncate text-xs text-muted-foreground">{user?.role_names.map((r) => r.replace(/_/g, " ").toLowerCase()).join(", ")}</span>
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="truncate">{user?.email}</DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem render={<Link href="/profile" />}><UserIcon className="size-4" /> My profile</DropdownMenuItem>
        <DropdownMenuItem onClick={() => void logout()}><LogOut className="size-4" /> Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function Topbar() {
  const [drawer, setDrawer] = useState(false)
  return (
    <header className={cn("no-print sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-3 backdrop-blur sm:px-5")}>
      <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" onClick={() => setDrawer(true)}>
        <Menu className="size-5" />
      </Button>
      <Sheet open={drawer} onOpenChange={setDrawer}>
        <SheetContent side="left" className="w-72 gap-0 bg-sidebar p-0 sm:max-w-72">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SheetDescription className="sr-only">Main navigation menu</SheetDescription>
          <Brand />
          <div className="flex-1 overflow-y-auto pb-6"><SidebarNav onNavigate={() => setDrawer(false)} /></div>
        </SheetContent>
      </Sheet>
      <GlobalSearch />
      <div className="ml-auto flex items-center gap-0.5">
        <LanguageToggle />
        <ThemeToggle />
        <NotificationBell />
        <UserMenu />
      </div>
    </header>
  )
}
