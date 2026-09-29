"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import type { ReactNode } from "react";

export interface DialogHandle {
  showModal: () => void;
  close: () => void;
}

interface DialogProps {
  titleId: string;
  title: string;
  children: ReactNode;
}

export const Dialog = forwardRef<DialogHandle, DialogProps>(function Dialog(
  { titleId, title, children },
  ref,
) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useImperativeHandle(ref, () => ({
    showModal: () => dialogRef.current?.showModal(),
    close: () => dialogRef.current?.close(),
  }));

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      className="w-full max-w-md rounded-lg border border-border bg-card p-6 text-card-foreground shadow-lg backdrop:bg-black/50"
    >
      <h2 id={titleId} className="mb-4 text-lg font-semibold">
        {title}
      </h2>
      {children}
    </dialog>
  );
});
