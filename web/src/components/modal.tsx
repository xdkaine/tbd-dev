"use client";

import { useCallback, useEffect, useId, useRef } from "react";

/* ---------------------------------------------------------------------- */
/*  Reusable Modal component                                               */
/* ---------------------------------------------------------------------- */

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  /** Optional override for aria-labelledby (defaults to auto-generated id) */
  ariaLabelledBy?: string;
}

/** Backdrop + centered panel. Closes on Escape or backdrop click. */
export function Modal({ open, onClose, children, ariaLabelledBy }: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const autoId = useId();
  const labelId = ariaLabelledBy ?? `modal-title-${autoId}`;

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }

      // Focus trap: Tab / Shift+Tab cycles within the modal
      if (e.key === "Tab" && panelRef.current) {
        const focusable = panelRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    },
    [onClose],
  );

  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement | null;
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";

      // Move focus into the modal panel
      requestAnimationFrame(() => {
        if (panelRef.current) {
          const firstFocusable = panelRef.current.querySelector<HTMLElement>(
            'a[href], button:not([disabled]), textarea, input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
          );
          if (firstFocusable) firstFocusable.focus();
          else panelRef.current.focus();
        }
      });
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";

      // Restore focus to the element that opened the modal
      if (previousFocusRef.current && typeof previousFocusRef.current.focus === "function") {
        previousFocusRef.current.focus();
      }
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
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
        tabIndex={-1}
        className="w-full max-w-md rounded-lg bg-zinc-900 border border-zinc-800 shadow-lg shadow-black/50 outline-none"
      >
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
  const titleId = useId();

  return (
    <Modal open={open} onClose={onClose} ariaLabelledBy={titleId}>
      <div className="p-6">
        <h3
          id={titleId}
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
