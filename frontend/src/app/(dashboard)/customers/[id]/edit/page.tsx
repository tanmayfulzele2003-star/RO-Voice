import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { CustomerForm } from "@/components/sections/CustomerForm";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { Customer } from "@/types/api";

export const metadata: Metadata = {
  title: "Edit customer",
};

export default async function EditCustomerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let customer: Customer | null = null;
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    customer = await apiClient.getCustomer(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load customer.";
  }

  return (
    <PageShell title="Edit customer" description={customer?.name}>
      {loadError || !customer ? (
        <ErrorState message={loadError ?? "Failed to load customer."} />
      ) : (
        <Card className="max-w-lg">
          <CustomerForm mode="edit" customer={customer} />
        </Card>
      )}
    </PageShell>
  );
}
