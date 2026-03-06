"use client";

import { useCallback, useEffect, useRef } from "react";

/* ---------------------------------------------------------------------- */
/*  Reusable Modal component                                               */
/* ---------------------------------------------------------------------- */

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}

/** Backdrop + centered panel. Closes on Escape or backdrop click. */
export function Modal({ open, onClose, children }: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <div className="w-full max-w-md rounded-lg bg-zinc-900 border border-zinc-800 shadow-lg shadow-black/50">
        {children}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  ConfirmModal — drop-in replacement for browser confirm()               */
/* ---------------------------------------------------------------------- */

interface ConfirmModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "default";
  loading?: boolean;
}

export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "default",
  loading = false,
}: ConfirmModalProps) {
  const isDanger = variant === "danger";

  return (
    <Modal open={open} onClose={onClose}>
      <div className="p-6">
        <h3
          className={`text-lg font-semibold ${isDanger ? "text-red-400" : "text-zinc-100"}`}
        >
          {title}
        </h3>
        {description && (
          <p className="mt-2 text-sm text-zinc-500">{description}</p>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={loading}
            className="rounded-md border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800/50 disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 ${
              isDanger
                ? "bg-red-500 text-white hover:bg-red-400"
                : "bg-brand-500 text-black hover:bg-brand-400"
            }`}
          >
            {loading ? "..." : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
