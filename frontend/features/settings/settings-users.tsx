"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQuery } from "@tanstack/react-query"
import { Pencil, Plus, ShieldCheck, Trash2, UserX } from "lucide-react"
import { useMemo, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { ConfirmDialog, FormDialog, SubmitRow } from "@/components/shared/dialogs"
import { Field, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDateTime, humanize } from "@/lib/format"
import type { PermissionDef, Role, User } from "@/types/api"

const passwordProblem = (v: string): string | null => (v.length < 8 ? "Use at least 8 characters" : !/[A-Za-z]/.test(v) || !/\d/.test(v) ? "Include letters and numbers" : null)
const createSchema = z.object({
  full_name: z.string().trim().min(2, "Enter the full name").max(150),
  email: z.string().trim().min(1, "Email is required").email("Enter a valid email"),
  phone: z.string().optional(),
  password: z.string(),
  role_id: z.string().min(1, "Choose a role"),
  max_discount_percent: z.string().optional(),
  must_change_password: z.boolean(),
})
type CreateValues = z.infer<typeof createSchema>

const useRoles = () => useQuery({ queryKey: ["roles"], queryFn: () => api.get<Role[]>("/roles"), staleTime: 30_000 })

function UserDialog({ user, onClose }: { user: User | "new" | null; onClose: () => void }) {
  const { user: me } = useAuth()
  const roles = useRoles()
  const editing = user && user !== "new" ? user : null
  const [serverError, setServerError] = useState<string | null>(null)
  const { register, handleSubmit, setError, formState: { errors } } = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    values: editing
      ? { full_name: editing.full_name, email: editing.email, phone: editing.phone ?? "", password: "", role_id: String(roles.data?.find((r) => r.name === editing.role_names[0])?.id ?? ""), max_discount_percent: editing.max_discount_percent === null ? "" : String(editing.max_discount_percent), must_change_password: false }
      : { full_name: "", email: "", phone: "", password: "", role_id: "", max_discount_percent: "", must_change_password: true },
  })
  const save = useApiMutation(
    (v: CreateValues) => {
      const body: Record<string, unknown> = { full_name: v.full_name, phone: v.phone || null, role_ids: [Number(v.role_id)], max_discount_percent: v.max_discount_percent === "" || v.max_discount_percent === undefined ? null : Number(v.max_discount_percent) }
      if (editing) { if (v.password) body.password = v.password; return api.patch(`/users/${editing.id}`, body) }
      return api.post("/users", { ...body, email: v.email, password: v.password, must_change_password: v.must_change_password })
    },
    { success: "User saved", invalidate: [["users"]], onSuccess: onClose, silentError: true },
  )
  const assignable = roles.data?.filter((r) => r.name !== "SUPER_ADMIN" || me?.role_names.includes("SUPER_ADMIN"))
  return (
    <FormDialog open={!!user} onOpenChange={(o) => !o && onClose()} title={editing ? "Edit user" : "New user"} description={editing ? "Leave the password blank to keep it unchanged." : "The user can sign in immediately."}>
      <form onSubmit={handleSubmit(async (v) => {
        setServerError(null)
        const problem = editing && !v.password ? null : passwordProblem(v.password)
        if (problem) return setError("password", { message: problem })
        try { await save.mutateAsync(v) } catch (e) { setServerError((e as Error).message) }
      })} className="space-y-4" noValidate>
        {serverError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{serverError}</div>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name" required error={errors.full_name?.message}>{(p) => <Input {...p} autoFocus {...register("full_name")} />}</Field>
          <Field label="Email" required error={errors.email?.message}>{(p) => <Input {...p} type="email" disabled={!!editing} {...register("email")} />}</Field>
          <Field label="Phone">{(p) => <Input {...p} type="tel" {...register("phone")} />}</Field>
          <Field label="Role" required error={errors.role_id?.message}>{(p) => (
            <select {...p} {...register("role_id")} className="h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm dark:bg-input/30"><option value="">Select…</option>{assignable?.map((r) => <option key={r.id} value={r.id}>{humanize(r.name.toLowerCase())}</option>)}</select>
          )}</Field>
          <Field label={editing ? "New password" : "Password"} required={!editing} error={errors.password?.message} hint="8+ characters with letters and numbers">{(p) => <Input {...p} type="password" autoComplete="new-password" {...register("password")} />}</Field>
          <Field label="Discount limit override (%)" hint="Empty = use the shop default">{(p) => <Input {...p} type="number" min="0" max="100" step="0.5" {...register("max_discount_percent")} />}</Field>
        </div>
        {!editing && <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" {...register("must_change_password")} /> Ask the user to change the password at first sign-in</label>}
        <SubmitRow onCancel={onClose} submitting={save.isPending} />
      </form>
    </FormDialog>
  )
}

export function UsersSettings() {
  const { can, user: me } = useAuth()
  const [dialog, setDialog] = useState<User | "new" | null>(null)
  const [del, setDel] = useState<User | null>(null)
  const { query, data, setPage, search, setSearch } = useTableQuery<User>("users", "/users")
  const toggle = useApiMutation((u: User) => api.patch(`/users/${u.id}`, { is_active: !u.is_active }), { success: "User updated", invalidate: [["users"]] })
  const remove = useApiMutation((u: User) => api.delete(`/users/${u.id}`), { success: "User removed", invalidate: [["users"]] })
  return (
    <>
      <div className="mb-4 flex items-end justify-between gap-3">
        <div><h2 className="text-base font-semibold">Users</h2><p className="text-sm text-muted-foreground">People who can sign in. Their role decides what they can see and do.</p></div>
        {can("user.create") && <Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add user</Button>}
      </div>
      <Toolbar><SearchInput value={search} onChange={setSearch} placeholder="Search name or email…" /></Toolbar>
      <DataTable<User>
        caption="Users" page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(u) => u.id}
        empty={{ title: "No users found." }}
        columns={[
          { id: "n", header: "User", cell: (u) => <div><div className="font-medium">{u.full_name}{u.id === me?.id && <span className="ml-2 text-xs text-muted-foreground">(you)</span>}</div><div className="text-xs text-muted-foreground">{u.email}</div></div> },
          { id: "r", header: "Role", cell: (u) => u.role_names.map((r) => humanize(r.toLowerCase())).join(", ") },
          { id: "2fa", header: "2FA", cell: (u) => (u.totp_enabled ? <ShieldCheck className="size-4 text-success" aria-label="Enabled" /> : <span className="text-muted-foreground">—</span>), hideOnMobile: true },
          { id: "l", header: "Last sign-in", cell: (u) => (u.last_login_at ? formatDateTime(u.last_login_at) : "never"), hideOnMobile: true },
          { id: "s", header: "Status", cell: (u) => <StatusBadge status={u.is_active ? "ACTIVE" : "INACTIVE"} /> },
          { id: "a", header: <span className="sr-only">Actions</span>, align: "right", cell: (u) => (
            <div className="flex justify-end gap-1">
              {can("user.update") && <Button variant="ghost" size="icon-sm" aria-label={`Edit ${u.full_name}`} onClick={() => setDialog(u)}><Pencil className="size-4" /></Button>}
              {can("user.update") && u.id !== me?.id && <Button variant="ghost" size="icon-sm" aria-label={u.is_active ? `Deactivate ${u.full_name}` : `Activate ${u.full_name}`} onClick={() => toggle.mutate(u)}><UserX className="size-4" /></Button>}
              {can("user.delete") && u.id !== me?.id && <Button variant="ghost" size="icon-sm" aria-label={`Remove ${u.full_name}`} onClick={() => setDel(u)}><Trash2 className="size-4" /></Button>}
            </div>) },
        ]}
      />
      <UserDialog user={dialog} onClose={() => setDialog(null)} />
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Remove ${del?.full_name}?`} description="They can no longer sign in and their sessions end immediately. Their past sales and audit history remain." confirmLabel="Remove user" destructive onConfirm={() => remove.mutateAsync(del!)} />
    </>
  )
}

/* ---------------------------------- roles ---------------------------------- */

export function RolesSettings() {
  const { can } = useAuth()
  const roles = useRoles()
  const perms = useQuery({ queryKey: ["permissions"], queryFn: () => api.get<PermissionDef[]>("/permissions"), staleTime: 300_000 })
  const [selected, setSelected] = useState<number | null>(null)
  const [draft, setDraft] = useState<Set<string> | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState("")
  const [del, setDel] = useState<Role | null>(null)
  const role = roles.data?.find((r) => r.id === (selected ?? roles.data?.[0]?.id))
  const editable = can("role.manage") && !!role && role.name !== "SUPER_ADMIN"
  const current = draft ?? new Set(role?.permissions ?? [])
  const grouped = useMemo(() => {
    const m = new Map<string, PermissionDef[]>()
    for (const p of perms.data ?? []) m.set(p.module, [...(m.get(p.module) ?? []), p])
    return [...m.entries()]
  }, [perms.data])
  const save = useApiMutation(() => api.patch(`/roles/${role!.id}`, { permissions: [...current] }), { success: "Permissions saved", invalidate: [["roles"]], onSuccess: () => setDraft(null) })
  const create = useApiMutation(() => api.post<Role>("/roles", { name: newName, description: "Custom role", permissions: [] }), { success: "Role created", invalidate: [["roles"]], onSuccess: (r) => { setCreating(false); setNewName(""); setSelected(r.id); setDraft(null) } })
  const remove = useApiMutation((r: Role) => api.delete(`/roles/${r.id}`), { success: "Role deleted", invalidate: [["roles"]], onSuccess: () => setSelected(null) })
  const toggle = (code: string, on: boolean) => { const next = new Set(current); if (on) next.add(code); else next.delete(code); setDraft(next) }

  return (
    <div className="grid gap-4 md:grid-cols-[240px_1fr]">
      <div>
        <div className="mb-2 flex items-center justify-between"><h2 className="text-base font-semibold">Roles</h2>{can("role.manage") && <Button size="sm" variant="outline" onClick={() => setCreating(true)}><Plus className="size-4" /> New</Button>}</div>
        <ul className="space-y-1" aria-label="Roles">
          {roles.data?.map((r) => (
            <li key={r.id}><button type="button" onClick={() => { setSelected(r.id); setDraft(null) }} aria-current={role?.id === r.id} className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${role?.id === r.id ? "bg-primary/10 font-medium text-primary" : "hover:bg-muted"}`}>
              {humanize(r.name.toLowerCase())}<span className="text-xs text-muted-foreground">{r.permissions.length}</span></button></li>
          ))}
        </ul>
      </div>
      <div className="rounded-xl border bg-card p-4">
        {role && (
          <>
            <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
              <div><h3 className="font-semibold">{humanize(role.name.toLowerCase())}</h3><p className="text-sm text-muted-foreground">{role.description}</p>{role.name === "SUPER_ADMIN" && <p className="mt-1 text-xs text-muted-foreground">The Super Admin always has every permission and cannot be edited.</p>}</div>
              <div className="flex gap-2">
                {editable && !role.is_system && <Button variant="outline" size="sm" onClick={() => setDel(role)}><Trash2 className="size-4" /> Delete</Button>}
                {editable && <Button size="sm" disabled={!draft || save.isPending} onClick={() => save.mutate()}>Save permissions</Button>}
              </div>
            </div>
            <div className="grid gap-x-8 gap-y-5 lg:grid-cols-2">
              {grouped.map(([module, list]) => (
                <fieldset key={module}><legend className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{module}</legend>
                  <div className="space-y-1">{list.map((p) => (
                    <label key={p.code} className="flex items-start gap-2 rounded-md px-1 py-1 text-sm hover:bg-muted/50">
                      <Checkbox checked={current.has(p.code)} disabled={!editable} onCheckedChange={(c) => toggle(p.code, !!c)} className="mt-0.5" />
                      <span><span className="font-mono text-xs">{p.code}</span><span className="block text-xs text-muted-foreground">{p.description}</span></span>
                    </label>))}</div>
                </fieldset>
              ))}
            </div>
          </>
        )}
      </div>
      <FormDialog open={creating} onOpenChange={setCreating} title="New role" description="Start empty, then tick the permissions this role needs." size="sm">
        <form onSubmit={(e) => { e.preventDefault(); if (newName.trim().length >= 2) create.mutate() }} className="space-y-4">
          <Field label="Role name" required>{(p) => <Input {...p} autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Shelf stocker" />}</Field>
          <SubmitRow onCancel={() => setCreating(false)} submitting={create.isPending} submitLabel="Create role" />
        </form>
      </FormDialog>
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete role ${del ? humanize(del.name.toLowerCase()) : ""}?`} description="Roles that are assigned to users cannot be deleted." confirmLabel="Delete role" destructive onConfirm={() => remove.mutateAsync(del!)} />
    </div>
  )
}
