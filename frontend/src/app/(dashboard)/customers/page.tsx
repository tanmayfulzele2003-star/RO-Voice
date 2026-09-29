import Link from "next/link";
import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { AddCustomerDialog } from "@/components/sections/AddCustomerDialog";
import { StartCallButton } from "@/components/sections/StartCallButton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { ApiError, type makeApiClient } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import { formatDateTime, formatPhone } from "@/lib/formatters";

export const metadata: Metadata = {
  title: "Customers",
  description: "Manage customers and start outbound calls.",
};

const PAGE_SIZE = 20;

export default async function CustomersPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>;
}) {
  const { offset: offsetParam } = await searchParams;
  const offset = Math.max(0, Number(offsetParam ?? 0) || 0);

  let items: Awaited<ReturnType<ReturnType<typeof makeApiClient>["listCustomers"]>>["items"] = [];
  let total = 0;
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    const result = await apiClient.listCustomers({ limit: PAGE_SIZE, offset });
    items = result.items;
    total = result.total;
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load customers.";
  }

  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <PageShell
      title="Customers"
      description={`${total} customer${total === 1 ? "" : "s"} on file.`}
      actions={<AddCustomerDialog />}
    >
      {loadError ? (
        <ErrorState message={loadError} />
      ) : items.length === 0 ? (
        <EmptyState
          title="No customers yet"
          description="Add your first customer to start placing calls."
        />
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Phone</TH>
                <TH>Company</TH>
                <TH>Added</TH>
                <TH>Actions</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((customer) => (
                <TR key={customer.id}>
                  <TD className="font-medium text-foreground">{customer.name}</TD>
                  <TD>{formatPhone(customer.phone)}</TD>
                  <TD>{customer.company ?? "—"}</TD>
                  <TD>{formatDateTime(customer.created_at)}</TD>
                  <TD>
                    <div className="flex flex-wrap items-center gap-3">
                      <Link
                        href={`/customers/${customer.id}/edit`}
                        className="text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                      >
                        Edit
                      </Link>
                      <StartCallButton customerId={customer.id} />
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <div className="flex justify-end gap-2">
            <Link
              aria-disabled={!hasPrev}
              href={`/customers?offset=${Math.max(0, offset - PAGE_SIZE)}`}
              className={`rounded-lg border border-border px-3 py-1.5 text-sm ${
                hasPrev ? "hover:bg-muted" : "pointer-events-none opacity-50"
              }`}
            >
              Previous
            </Link>
            <Link
              aria-disabled={!hasNext}
              href={`/customers?offset=${offset + PAGE_SIZE}`}
              className={`rounded-lg border border-border px-3 py-1.5 text-sm ${
                hasNext ? "hover:bg-muted" : "pointer-events-none opacity-50"
              }`}
            >
              Next
            </Link>
          </div>
        </>
      )}
    </PageShell>
  );
}
