import { EntityDetail } from "@/components/career/entity-detail";

export default async function CareerEntityPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <EntityDetail entityId={id} />;
}
