"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQuery } from "@tanstack/react-query"
import { LogIn, LogOut, Pencil, Plus } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { DataTable, SearchInput, Toolbar } from "@/components/shared/data-table"
import { FormDialog, SubmitRow } from "@/components/shared/dialogs"
import { Can, Field, KeyValue, Money, NativeSelect, PageHeader, PageLoading, SectionCard, StatCard, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useTableQuery } from "@/hooks/use-table-query"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDate, formatDateTime, formatNumber, humanize } from "@/lib/format"
import { optionalNumber } from "@/services/lookups"
import type { Employee, Page, User } from "@/types/api"

const PHONE = /^[+0-9][0-9\-\s()]{5,24}$/
const schema = z.object({
  full_name: z.string().trim().min(1, "Name is required").max(150),
  phone: z.string().trim().optional().refine((v) => !v || PHONE.test(v), "Enter a valid phone number"),
  email: z.string().trim().optional().refine((v) => !v || /^\S+@\S+\.\S+$/.test(v), "Enter a valid email"),
  address: z.string().optional(),
  position: z.string().trim().max(100).optional(),
  joining_date: z.string().optional(),
  status: z.enum(["ACTIVE", "INACTIVE", "TERMINATED"]),
  salary: z.number().min(0, "Cannot be negative").optional(),
  national_id: z.string().max(50).optional(),
  user_id: z.number().optional(),
})
type Values = z.infer<typeof schema>

function EmployeeDialog({ employee, onClose }: { employee: Employee | "new" | null; onClose: () => void }) {
  const { can } = useAuth()
  const editing = employee && employee !== "new" ? employee : null
  const users = useQuery({ queryKey: ["users", "options"], queryFn: () => api.get<Page<User>>("/users", { page_size: 100 }), enabled: !!employee && can("user.read") })
  const salaryOk = can("employee.salary")
  const [serverError, setServerError] = useState<string | null>(null)
  const { register, handleSubmit, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    values: editing
      ? { full_name: editing.full_name, phone: editing.phone ?? "", email: editing.email ?? "", address: editing.address ?? "", position: editing.position ?? "", joining_date: editing.joining_date ?? "", status: editing.status as Values["status"], salary: editing.salary ?? undefined, national_id: editing.national_id ?? "", user_id: editing.user_id ?? undefined }
      : { full_name: "", phone: "", email: "", address: "", position: "", joining_date: "", status: "ACTIVE", salary: 0, national_id: "" },
  })
  const save = useApiMutation(
    (v: Values) => {
      const body: Record<string, unknown> = {}
      for (const [k, val] of Object.entries(v)) body[k] = val === "" || Number.isNaN(val) ? null : val
      if (!salaryOk) { delete body.salary; delete body.national_id }
      return editing ? api.patch(`/employees/${editing.id}`, body) : api.post("/employees", body)
    },
    { success: "Employee saved", invalidate: [["employees"]], onSuccess: onClose, silentError: true },
  )
  return (
    <FormDialog open={!!employee} onOpenChange={(o) => !o && onClose()} title={editing ? "Edit employee" : "New employee"} size="lg">
      <form onSubmit={handleSubmit(async (v) => { setServerError(null); try { await save.mutateAsync(v) } catch (e) { setServerError((e as Error).message) } })} className="space-y-4" noValidate>
        {serverError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{serverError}</div>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name" required error={errors.full_name?.message}>{(p) => <Input {...p} autoFocus {...register("full_name")} />}</Field>
          <Field label="Position">{(p) => <Input {...p} {...register("position")} />}</Field>
          <Field label="Phone" error={errors.phone?.message}>{(p) => <Input {...p} type="tel" {...register("phone")} />}</Field>
          <Field label="Email" error={errors.email?.message}>{(p) => <Input {...p} type="email" {...register("email")} />}</Field>
          <Field label="Joining date">{(p) => <Input {...p} type="date" {...register("joining_date")} />}</Field>
          <Field label="Status">{(p) => <NativeSelect {...p} {...register("status")}><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option><option value="TERMINATED">Terminated</option></NativeSelect>}</Field>
          {salaryOk && <Field label="Monthly salary (৳)" error={errors.salary?.message}>{(p) => <Input {...p} type="number" min="0" step="0.01" {...register("salary", { setValueAs: optionalNumber })} />}</Field>}
          {salaryOk && <Field label="National ID">{(p) => <Input {...p} {...register("national_id")} />}</Field>}
          {can("user.read") && <Field label="Linked login account" hint="Lets sales and actions be traced to this person">{(p) => <NativeSelect {...p} {...register("user_id", { setValueAs: optionalNumber })}><option value="">— None —</option>{users.data?.items.map((u) => <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>)}</NativeSelect>}</Field>}
          <Field label="Address" className="sm:col-span-2">{(p) => <Textarea {...p} rows={2} {...register("address")} />}</Field>
        </div>
        <SubmitRow onCancel={onClose} submitting={save.isPending} />
      </form>
    </FormDialog>
  )
}

export function EmployeesList() {
  const router = useRouter()
  const { can } = useAuth()
  const [dialog, setDialog] = useState<Employee | "new" | null>(null)
  const [status, setStatus] = useState("")
  const { query, data, setPage, search, setSearch } = useTableQuery<Employee>("employees", "/employees", { filters: { status: status || undefined } })
  return (
    <>
      <PageHeader title="Employees" description="Staff profiles, linked logins and activity." actions={<Can perm="employee.create"><Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add employee</Button></Can>} />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search name, code or phone…" />
        <NativeSelect aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-36"><option value="">All statuses</option><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option><option value="TERMINATED">Terminated</option></NativeSelect>
      </Toolbar>
      <DataTable<Employee>
        caption="Employees" page={data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} onPageChange={setPage} rowKey={(e) => e.id} onRowClick={(e) => router.push(`/employees/${e.id}`)}
        empty={{ title: "No employees found.", action: can("employee.create") ? <Button onClick={() => setDialog("new")}><Plus className="size-4" /> Add employee</Button> : undefined }}
        columns={[
          { id: "code", header: "ID", cell: (e) => <span className="font-mono text-xs">{e.employee_code}</span> },
          { id: "name", header: "Name", cell: (e) => <span className="font-medium">{e.full_name}</span> },
          { id: "pos", header: "Position", cell: (e) => e.position ?? "—", hideOnMobile: true },
          { id: "phone", header: "Phone", cell: (e) => e.phone ?? "—", hideOnMobile: true },
          { id: "login", header: "Login", cell: (e) => e.user_email ?? <span className="text-muted-foreground">none</span>, hideOnMobile: true },
          ...(can("employee.salary") ? [{ id: "salary", header: "Salary", align: "right" as const, cell: (e: Employee) => <Money value={e.salary} />, hideOnMobile: true }] : []),
          { id: "status", header: "Status", cell: (e) => <StatusBadge status={e.status} /> },
        ]}
      />
      <EmployeeDialog employee={dialog} onClose={() => setDialog(null)} />
    </>
  )
}

interface Activity { sales_count: number; sales_total: number; sessions_count: number; voids_count: number; recent_actions: { at: string; action: string; entity: string; entity_id: string | null }[] }
interface Attendance { id: number; work_date: string; check_in: string | null; check_out: string | null; status: string }

export function EmployeeProfile({ id }: { id: number }) {
  const { can } = useAuth()
  const { data: e, isLoading, error } = useQuery({ queryKey: ["employees", "detail", id], queryFn: () => api.get<Employee>(`/employees/${id}`) })
  const activity = useQuery({ queryKey: ["employees", "activity", id], queryFn: () => api.get<Activity>(`/employees/${id}/activity`) })
  const att = useQuery({ queryKey: ["employees", "attendance", id], queryFn: () => api.get<Attendance[]>(`/employees/${id}/attendance`) })
  const [edit, setEdit] = useState(false)
  const checkIn = useApiMutation(() => api.post(`/employees/${id}/attendance/check-in`), { success: "Checked in", invalidate: [["employees", "attendance", id]] })
  const checkOut = useApiMutation(() => api.post(`/employees/${id}/attendance/check-out`), { success: "Checked out", invalidate: [["employees", "attendance", id]] })
  if (isLoading) return <PageLoading />
  if (error || !e) return <p className="mt-10 text-center text-sm text-muted-foreground" role="alert">{errorMessage(error ?? new Error("Employee not found"))}</p>
  const a = activity.data
  return (
    <>
      <PageHeader back={{ href: "/employees", label: "Employees" }} title={e.full_name} description={<span className="flex items-center gap-3"><span className="font-mono text-xs">{e.employee_code}</span>{e.position}<StatusBadge status={e.status} /></span>}
        actions={<Can perm="employee.update"><Button variant="outline" onClick={() => setEdit(true)}><Pencil className="size-4" /> Edit</Button></Can>} />
      <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard label="Sales made" value={a ? formatNumber(a.sales_count, 0) : "—"} loading={activity.isLoading} />
        <StatCard label="Sales value" value={<Money value={a?.sales_total} />} loading={activity.isLoading} />
        <StatCard label="Register sessions" value={a ? formatNumber(a.sessions_count, 0) : "—"} loading={activity.isLoading} />
        <StatCard label="Sales voided" value={a ? formatNumber(a.voids_count, 0) : "—"} tone={a && a.voids_count > 0 ? "warning" : "neutral"} loading={activity.isLoading} />
      </div>
      <Tabs defaultValue="details">
        <TabsList className="mb-4"><TabsTrigger value="details">Details</TabsTrigger><TabsTrigger value="activity">Recent actions</TabsTrigger><TabsTrigger value="attendance">Attendance</TabsTrigger></TabsList>
        <TabsContent value="details">
          <SectionCard title="Profile"><dl className="grid gap-x-8 md:grid-cols-2">
            <KeyValue label="Phone">{e.phone ?? "—"}</KeyValue><KeyValue label="Email">{e.email ?? "—"}</KeyValue>
            <KeyValue label="Joined">{formatDate(e.joining_date)}</KeyValue><KeyValue label="Login account">{e.user_email ?? "none"}</KeyValue>
            {e.salary !== null && <KeyValue label="Salary"><Money value={e.salary} /></KeyValue>}
            {e.national_id && <KeyValue label="National ID">{e.national_id}</KeyValue>}
            <KeyValue label="Address">{e.address ?? "—"}</KeyValue>
          </dl></SectionCard>
        </TabsContent>
        <TabsContent value="activity">
          <SectionCard title="Latest actions in the system">
            {!a?.recent_actions.length ? <p className="py-6 text-center text-sm text-muted-foreground">{e.user_id ? "No recorded actions yet." : "This employee has no login account, so no actions are tracked."}</p> : (
              <ul className="divide-y">{a.recent_actions.map((r, i) => <li key={i} className="flex items-center justify-between py-2 text-sm"><span><span className="font-medium">{humanize(r.action)}</span> <span className="text-muted-foreground">· {r.entity}{r.entity_id ? ` #${r.entity_id}` : ""}</span></span><span className="text-xs text-muted-foreground">{formatDateTime(r.at)}</span></li>)}</ul>
            )}
          </SectionCard>
        </TabsContent>
        <TabsContent value="attendance">
          <SectionCard title="Attendance" actions={<Can perm="employee.update"><div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => checkIn.mutate()}><LogIn className="size-4" /> Check in</Button><Button size="sm" variant="outline" onClick={() => checkOut.mutate()}><LogOut className="size-4" /> Check out</Button></div></Can>}>
            {!att.data?.length ? <p className="py-6 text-center text-sm text-muted-foreground">No attendance recorded.</p> : (
              <ul className="divide-y">{att.data.map((r) => <li key={r.id} className="flex items-center justify-between py-2 text-sm"><span>{formatDate(r.work_date)}</span><span className="text-muted-foreground">{r.check_in ? formatDateTime(r.check_in) : "—"} → {r.check_out ? formatDateTime(r.check_out) : "…"}</span><StatusBadge status={r.status} /></li>)}</ul>
            )}
          </SectionCard>
        </TabsContent>
      </Tabs>
      <EmployeeDialog employee={edit ? e : null} onClose={() => setEdit(false)} />
    </>
  )
}
