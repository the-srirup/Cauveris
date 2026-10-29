"use client";

import { useEffect, useRef, type ReactNode, forwardRef } from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";

export interface DialogProps {
  /** Whether dialog is open */
  open: boolean;
  /** Called when dialog should close */
  onClose: () => void;
  /** Dialog title */
  title?: string;
  /** Dialog description */
  description?: string;
  /** Dialog content */
  children?: ReactNode;
  /** Footer actions */
  footer?: ReactNode;
  /** Dialog size */
  size?: "sm" | "md" | "lg" | "xl" | "full";
  /** Whether to show close button */
  showCloseButton?: boolean;
  /** Whether clicking overlay closes dialog */
  closeOnOverlayClick?: boolean;
  /** Whether pressing Escape closes dialog */
  closeOnEscape?: boolean;
  /** Additional class names */
  className?: string;
  /** ARIA label for dialog */
  "aria-label"?: string;
  /** Element to return focus to after close */
  returnFocusRef?: React.RefObject<HTMLElement>;
  /** Whether dialog is modal (blocks interaction with rest of page) */
  modal?: boolean;
}

const sizeClasses = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
  full: "max-w-[90vw] w-[90vw]",
};

export const Dialog = forwardRef<HTMLDivElement, DialogProps>(
  (
    {
      open,
      onClose,
      title,
      description,
      children,
      footer,
      size = "md",
      showCloseButton = true,
      closeOnOverlayClick = true,
      closeOnEscape = true,
      className = "",
      "aria-label": ariaLabel,
      returnFocusRef,
      modal = true,
    },
    ref
  ) => {
    const dialogRef = useRef<HTMLDivElement>(null);
    const previousActiveElement = useRef<HTMLElement | null>(null);

    // Attach forwarded ref
    useEffect(() => {
      if (ref) {
        if (typeof ref === "function") {
          ref(dialogRef.current);
        } else {
          ref.current = dialogRef.current;
        }
      }
    }, [ref]);

    // Handle Escape key
    useEffect(() => {
      if (!open) return;
      function handleKeyDown(event: KeyboardEvent) {
        if (event.key === "Escape" && closeOnEscape) {
          onClose();
        }
      }

      document.addEventListener("keydown", handleKeyDown);
      previousActiveElement.current = document.activeElement as HTMLElement;
      // Focus the dialog
      setTimeout(() => dialogRef.current?.focus(), 0);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }, [open, closeOnEscape]);

    // Handle focus trap
    useEffect(() => {
      if (!open || !dialogRef.current) return;

      const dialog = dialogRef.current;
      const focusableElements = dialog.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      function handleTabKey(event: KeyboardEvent) {
        if (event.key !== "Tab") return;

        if (event.shiftKey) {
          if (document.activeElement === firstElement) {
            event.preventDefault();
            lastElement?.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            event.preventDefault();
            firstElement?.focus();
          }
        }
      }

      dialog.addEventListener("keydown", handleTabKey);
      firstElement?.focus();

      return () => dialog.removeEventListener("keydown", handleTabKey);
    }, [open, children]);

    // Return focus on close
    useEffect(() => {
      if (!open) {
        returnFocusRef?.current?.focus() ?? previousActiveElement.current?.focus();
      }
    }, [open]);

    // Prevent body scroll when open
    useEffect(() => {
      if (open && modal) {
        document.body.style.overflow = "hidden";
      }
      return () => {
        document.body.style.overflow = "";
      };
    }, [open, modal]);

    if (!open) return null;

    const dialogContent = (
      <div
        className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-black/70 backdrop-blur-xs animate-fade-in"
        onClick={closeOnOverlayClick ? onClose : undefined}
        role="presentation"
        onKeyDown={(e) => e.stopPropagation()}
      >
        <div
          ref={dialogRef}
          onClick={(e) => e.stopPropagation()}
          className={`relative w-full max-h-[85vh] overflow-y-auto bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] rounded-[var(--radius-xl,10px)] shadow-[var(--shadow-xl)] animate-scale-in my-auto ${sizeClasses[size]} ${className}`}
          role="dialog"
          aria-modal={modal ? "true" : "false"}
          aria-labelledby={title ? "dialog-title" : undefined}
          aria-describedby={description ? "dialog-description" : undefined}
          aria-label={!title && ariaLabel ? ariaLabel : undefined}
          tabIndex={-1}
        >
          <div className="flex flex-col">
            {(title || showCloseButton) && (
              <div className="flex items-start justify-between gap-3 p-4 border-b border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]">
                <div className="flex-1 min-w-0">
                  {title && (
                    <h2 id="dialog-title" className="text-lg font-semibold text-[var(--color-fg-default)]">
                      {title}
                    </h2>
                  )}
                  {description && (
                    <p id="dialog-description" className="mt-1 text-sm text-[var(--color-fg-muted)]">
                      {description}
                    </p>
                  )}
                </div>
                {showCloseButton && (
                  <button
                    type="button"
                    onClick={onClose}
                    className={`
                      flex-shrink-0 p-1 text-[var(--color-fg-muted)]
                      hover:text-[var(--color-fg-default)]
                      hover:bg-[var(--color-canvas-subtle)]
                      rounded-[var(--radius-sm)]
                      transition-colors duration-80 ease-out
                      focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)]
                    `}
                    aria-label="Close dialog"
                  >
                    <svg className="h-5 w-5" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                      <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.75.75 0 1 1 1.06 1.06L9.06 8l3.22 3.22a.75.75 0 1 1-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 0 1-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06z" />
                    </svg>
                  </button>
                )}
              </div>
            )}
            <div className="p-4 overflow-y-auto">{children}</div>
            {footer && (
              <div className="flex items-center justify-end gap-3 p-4 border-t border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)/50] rounded-b-[var(--radius-lg)]">
                {footer}
              </div>
            )}
          </div>
        </div>
      </div>
    );

    if (typeof window === "undefined") return null;
    return createPortal(dialogContent, document.body);
  }
);

Dialog.displayName = "Dialog";

// Confirm Dialog
export interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  variant?: "danger" | "primary" | "secondary";
  loading?: boolean;
  size?: "sm" | "md";
}

export function ConfirmDialog({
  open,
  onClose,
  title,
  description,
  confirmText = "Confirm",
  cancelText = "Cancel",
  onConfirm,
  variant = "primary",
  loading = false,
  size = "sm",
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      size={size}
      footer={
        <>
          <Button variant="ghost" size="md" onClick={onClose} disabled={loading}>
            {cancelText}
          </Button>
          <Button variant={variant === "danger" ? "danger" : variant} size="md" onClick={onConfirm} disabled={loading} autoFocus>
            {confirmText}
          </Button>
        </>
      }
    />
  );
}

// Form Dialog
export interface FormDialogProps extends Omit<DialogProps, "footer"> {
  /** Form submit handler */
  onSubmit: (data: FormData) => void;
  /** Submit button text */
  submitText?: string;
  /** Cancel button text */
  cancelText?: string;
  /** Whether form is submitting */
  submitting?: boolean;
}

export function FormDialog({
  open,
  onClose,
  title,
  description,
  children,
  onSubmit,
  submitText = "Save",
  cancelText = "Cancel",
  submitting = false,
  size = "md",
  ...props
}: FormDialogProps) {
  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    onSubmit(formData);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      size={size}
      footer={
        <form onSubmit={handleSubmit}>
          <Button type="button" variant="ghost" size="md" onClick={onClose} disabled={submitting}>
            {cancelText}
          </Button>
          <Button type="submit" variant="primary" size="md" disabled={submitting} autoFocus>
            {submitting ? "Saving..." : submitText}
          </Button>
        </form>
      }
      {...props}
    >
      {children}
    </Dialog>
  );
}