import { RequirePermission } from "@/components/shared/ui-parts"
import { BrandsPage } from "@/features/products/taxonomy"

export const metadata = { title: "Brands" }

export default function Page() {
  return <RequirePermission any={["product.read"]}><BrandsPage /></RequirePermission>
}
