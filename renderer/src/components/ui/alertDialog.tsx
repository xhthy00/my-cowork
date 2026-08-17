/**
 * Adapted from eigent: alertDialog pattern (lightweight modal).
 */
import { Button } from "./button";
import { cn } from "@/lib/utils";

interface AlertDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: "primary" | "destructive";
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children?: React.ReactNode;
}

export default function AlertDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  confirmVariant = "primary",
  confirmDisabled = false,
  onConfirm,
  onCancel,
  children,
}: AlertDialogProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 p-4">
      <div
        className={cn(
          "w-full max-w-md rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-5 shadow-perfect",
        )}
        role="dialog"
        aria-modal="true"
      >
        <h3 className="text-base font-semibold text-[var(--text)]">{title}</h3>
        {description && (
          <p className="mt-2 text-sm text-[var(--text-secondary)]">{description}</p>
        )}
        {children && <div className="mt-3">{children}</div>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant={confirmVariant === "destructive" ? "destructive" : "primary"}
            disabled={confirmDisabled}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
