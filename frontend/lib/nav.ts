import {
  BarChart3,
  Bell,
  Boxes,
  Landmark,
  LayoutDashboard,
  type LucideIcon,
  Package,
  ReceiptText,
  Settings,
  ShieldCheck,
  ShoppingCart,
  Truck,
  UserCog,
  Users,
  Wallet,
  Warehouse,
} from "lucide-react"

export interface NavChild {
  labelKey: string
  href: string
  perms: string[] // visible when the user holds ANY of these
}

export interface NavItem {
  labelKey: string
  href: string
  icon: LucideIcon
  perms: string[]
  children?: NavChild[]
}

export const NAV: NavItem[] = [
  { labelKey: "nav.dashboard", href: "/dashboard", icon: LayoutDashboard, perms: ["dashboard.view"] },
  { labelKey: "nav.pos", href: "/pos", icon: ShoppingCart, perms: ["sale.create"] },
  {
    labelKey: "nav.sales", href: "/sales", icon: ReceiptText, perms: ["sale.read"],
    children: [
      { labelKey: "nav.sales.all", href: "/sales", perms: ["sale.read"] },
      { labelKey: "nav.sales.returns", href: "/sales/returns", perms: ["sale.read"] },
      { labelKey: "nav.sales.discounts", href: "/sales/discount-requests", perms: ["discount.approve", "sale.create"] },
    ],
  },
  {
    labelKey: "nav.products", href: "/products", icon: Package, perms: ["product.read"],
    children: [
      { labelKey: "nav.products.all", href: "/products", perms: ["product.read"] },
      { labelKey: "nav.products.categories", href: "/products/categories", perms: ["product.read"] },
      { labelKey: "nav.products.brands", href: "/products/brands", perms: ["product.read"] },
      { labelKey: "nav.products.barcode", href: "/products/barcode", perms: ["product.read"] },
    ],
  },
  {
    labelKey: "nav.inventory", href: "/inventory", icon: Warehouse, perms: ["inventory.read"],
    children: [
      { labelKey: "nav.inventory.stock", href: "/inventory", perms: ["inventory.read"] },
      { labelKey: "nav.inventory.movements", href: "/inventory/movements", perms: ["inventory.read"] },
      { labelKey: "nav.inventory.low", href: "/inventory/low-stock", perms: ["inventory.read"] },
      { labelKey: "nav.inventory.expiring", href: "/inventory/expiring", perms: ["inventory.read"] },
      { labelKey: "nav.inventory.expired", href: "/inventory/expired", perms: ["inventory.read"] },
      { labelKey: "nav.inventory.adjustments", href: "/inventory/adjustments", perms: ["inventory.read"] },
    ],
  },
  {
    labelKey: "nav.purchases", href: "/purchases", icon: Boxes, perms: ["purchase.read"],
    children: [
      { labelKey: "nav.purchases.orders", href: "/purchases", perms: ["purchase.read"] },
      { labelKey: "nav.purchases.receive", href: "/purchases/receive", perms: ["purchase.receive"] },
      { labelKey: "nav.purchases.returns", href: "/purchases/returns", perms: ["purchase.read"] },
    ],
  },
  {
    labelKey: "nav.suppliers", href: "/suppliers", icon: Truck, perms: ["supplier.read"],
    children: [
      { labelKey: "nav.suppliers.list", href: "/suppliers", perms: ["supplier.read"] },
      { labelKey: "nav.suppliers.ledger", href: "/suppliers/ledger", perms: ["supplier.read"] },
    ],
  },
  {
    labelKey: "nav.customers", href: "/customers", icon: Users, perms: ["customer.read"],
    children: [
      { labelKey: "nav.customers.list", href: "/customers", perms: ["customer.read"] },
      { labelKey: "nav.customers.ledger", href: "/customers/ledger", perms: ["customer.read"] },
    ],
  },
  { labelKey: "nav.expenses", href: "/expenses", icon: Wallet, perms: ["expense.read"] },
  { labelKey: "nav.register", href: "/cash-register", icon: Landmark, perms: ["register.use", "register.manage"] },
  { labelKey: "nav.employees", href: "/employees", icon: UserCog, perms: ["employee.read"] },
  {
    labelKey: "nav.reports", href: "/reports/sales", icon: BarChart3, perms: ["report.sales", "report.inventory", "report.purchases", "report.profit", "report.expenses", "report.finance"],
    children: [
      { labelKey: "nav.reports.sales", href: "/reports/sales", perms: ["report.sales"] },
      { labelKey: "nav.reports.purchases", href: "/reports/purchases", perms: ["report.purchases"] },
      { labelKey: "nav.reports.inventory", href: "/reports/inventory", perms: ["report.inventory"] },
      { labelKey: "nav.reports.profit", href: "/reports/profit", perms: ["report.profit"] },
      { labelKey: "nav.reports.expenses", href: "/reports/expenses", perms: ["report.expenses"] },
      { labelKey: "nav.reports.cashflow", href: "/reports/cash-flow", perms: ["report.finance"] },
    ],
  },
  { labelKey: "nav.notifications", href: "/notifications", icon: Bell, perms: ["notification.read"] },
  { labelKey: "nav.audit", href: "/audit-logs", icon: ShieldCheck, perms: ["audit.read"] },
  { labelKey: "nav.settings", href: "/settings", icon: Settings, perms: ["settings.read", "user.read", "backup.manage", "role.manage", "promotion.manage", "import.manage"] },
]

export function visibleNav(can: (p: string) => boolean): NavItem[] {
  return NAV.filter((i) => i.perms.some(can)).map((i) => ({
    ...i,
    children: i.children?.filter((c) => c.perms.some(can)),
  }))
}

export function isActive(pathname: string, href: string, exact = false): boolean {
  if (exact) return pathname === href
  return pathname === href || pathname.startsWith(`${href}/`)
}
