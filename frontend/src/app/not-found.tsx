import Link from "next/link";
import { PageShell } from "@/components/layout/PageShell";
import { EmptyState } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";

export default function NotFound() {
  return (
    <PageShell title="Not found">
      <EmptyState
        title="We couldn't find that page"
        description="It may have been removed, or the link might be incorrect."
        action={
          <Link href="/">
            <Button variant="secondary">Back to overview</Button>
          </Link>
        }
      />
    </PageShell>
  );
}
