"use client";

import { useEffect, useRef, type ReactNode, forwardRef } from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";

export interface ModalProps {
  /** Whether modal is open */
  open: boolean;
  /** Called when modal should close */
  onClose: () => void;
  /** Modal title */
  title?: string;
  /** Modal subtitle/description */
  description?: string;
  /** Modal content */
  children?: ReactNode;
  /** Footer actions */
  footer?: ReactNode;
  /** Modal size */
  size?: "sm" | "md" | "lg" | "xl" | "full";
  /** Whether to show close button */
  showCloseButton?: boolean;
  /** Whether clicking overlay closes modal */
  closeOnOverlayClick?: boolean;
  /** Whether pressing Escape closes modal */
  closeOnEscape?: boolean;
  /** Additional class names */
  className?: string;
  /** ARIA label for modal */
  "aria-label"?: string;
  /** Element to return focus to after close */
  returnFocusRef?: React.RefObject<HTMLElement>;
}

const sizeClasses = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
  full: "max-w-4xl w-[90vw]",
};

export const Modal = forwardRef<HTMLDialogElement, ModalProps>(
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
    },
    ref
  ) => {
    const dialogRef = useRef<HTMLDialogElement>(null);
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
    }, [open]);

    // Return focus on close
    useEffect(() => {
      if (!open) {
        returnFocusRef?.current?.focus() ?? previousActiveElement.current?.focus();
      }
    }, [open]);

    if (!open) return null;

    const modalContent = (
      <div
        className="modal-overlay"
        onClick={closeOnOverlayClick ? onClose : undefined}
        role="presentation"
      >
        <dialog
          ref={dialogRef}
          className={`
            modal-dialog ${sizeClasses[size]} ${className}
          `}
          role="dialog"
          aria-modal="true"
          aria-labelledby={title ? "modal-title" : undefined}
          aria-describedby={description ? "modal-description" : undefined}
          aria-label={!title && ariaLabel ? ariaLabel : undefined}
          tabIndex={-1}
        >
          <style jsx>{`
            .modal-overlay {
              position: fixed;
              inset: 0;
              z-index: var(--z-modal);
              background: rgba(0, 0, 0, 0.5);
              animation: fade-in var(--duration-fast) var(--easing-standard);
            }
            .modal-dialog {
              position: fixed;
              z-index: var(--z-modal);
              top: 50%;
              left: 50%;
              transform: translate(-50%, -50%);
              width: 90%;
              max-height: 85vh;
              overflow-y: auto;
              background: var(--color-canvas-inset);
              border: 1px solid var(--color-border-default);
              border-radius: var(--radius-xl, 10px);
              box-shadow: var(--shadow-lg);
              animation: scale-in var(--duration-normal) var(--easing-emphasized);
            }
          `}</style>
          {(title || showCloseButton) && (
            <div className="modal-header">
              {title && (
                <h2 id="modal-title" className="modal-title">
                  {title}
                </h2>
              )}
              {showCloseButton && (
                <button
                  type="button"
                  onClick={onClose}
                  className={`
                    p-1 text-[var(--color-fg-muted)]
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
          {description && (
            <p id="modal-description" className="sr-only">
              {description}
            </p>
          )}
          <div className="modal-body">{children}</div>
          {footer && (
            <div className="modal-footer">{footer}</div>
          )}
        </dialog>
      </div>
    );

    if (typeof window === "undefined") return null;
    return createPortal(modalContent, document.body);
  }
);

Modal.displayName = "Modal";

// Alert Dialog - simpler confirmation dialog
export interface AlertDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  variant?: "danger" | "primary";
  loading?: boolean;
}

export function AlertDialog({
  open,
  onClose,
  title,
  description,
  confirmText = "Confirm",
  cancelText = "Cancel",
  onConfirm,
  variant = "primary",
  loading = false,
}: AlertDialogProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      size="sm"
      footer={
        <div className="modal-footer">
          <Button variant="ghost" size="md" onClick={onClose} disabled={loading}>
            {cancelText}
          </Button>
          <Button variant={variant === "danger" ? "danger" : "primary"} size="md" onClick={onConfirm} disabled={loading} autoFocus>
            {confirmText}
          </Button>
        </div>
      }
    />
  );
}