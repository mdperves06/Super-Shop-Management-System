import { RequirePermission } from "@/components/shared/ui-parts"
import { CategoriesPage } from "@/features/products/taxonomy"

export const metadata = { title: "Categories" }

export default function Page() {
  return <RequirePermission any={["product.read"]}><CategoriesPage /></RequirePermission>
}
