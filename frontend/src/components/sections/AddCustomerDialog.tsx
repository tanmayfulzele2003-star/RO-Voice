"use client";

import { useRef } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog, type DialogHandle } from "@/components/ui/Dialog";
import { CustomerForm } from "@/components/sections/CustomerForm";
import type { BusinessProfile } from "@/types/api";

export function AddCustomerDialog({ profiles }: { profiles: BusinessProfile[] }) {
  const dialogRef = useRef<DialogHandle>(null);

  return (
    <>
      <Button onClick={() => dialogRef.current?.showModal()}>Add customer</Button>
      <Dialog ref={dialogRef} titleId="add-customer-title" title="Add customer">
        <CustomerForm mode="create" profiles={profiles} onSuccess={() => dialogRef.current?.close()} />
      </Dialog>
    </>
  );
}
