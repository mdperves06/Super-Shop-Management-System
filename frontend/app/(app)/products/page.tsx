import { RequirePermission } from "@/components/shared/ui-parts"
import { ProductsList } from "@/features/products/products-list"

export const metadata = { title: "Products" }

export default function Page() {
  return <RequirePermission any={["product.read"]}><ProductsList /></RequirePermission>
}
