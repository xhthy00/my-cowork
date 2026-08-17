import * as React from "react";

import { cn } from "@/lib/utils";

type SettingsFieldProps = Omit<React.ComponentProps<"input">, "size"> & {
  title?: string;
  note?: React.ReactNode;
  state?: "default" | "error" | "success";
  backIcon?: React.ReactNode;
  onBackIconClick?: () => void;
};

/** Visual match for Eigent `Input` (title + rounded-xl field shell). */
export const SettingsField = React.forwardRef<HTMLInputElement, SettingsFieldProps>(
  function SettingsField(
    {
      title,
      note,
      state = "default",
      className,
      backIcon,
      onBackIconClick,
      ...props
    },
    ref,
  ) {
    return (
      <div className={cn("w-full min-w-0", className)}>
        {title ? (
          <div className="mb-1.5 flex items-center gap-1 text-body-sm font-bold text-ds-text-neutral-default-default">
            <span>{title}</span>
          </div>
        ) : null}
        <div
          className={cn(
            "relative flex h-10 items-center rounded-xl border border-solid shadow-sm transition-colors",
            state === "error"
              ? "border-ds-text-error-default-default bg-ds-bg-neutral-default-default"
              : state === "success"
                ? "border-ds-text-success-default-default bg-ds-bg-neutral-default-default"
                : [
                    "border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default",
                    "hover:bg-ds-bg-neutral-subtle-default",
                    "focus-within:bg-ds-bg-neutral-subtle-default focus-within:ring-1 focus-within:ring-ds-border-neutral-strong-default focus-within:ring-offset-0",
                  ],
          )}
        >
          <input
            ref={ref}
            className={cn(
              "peer w-full bg-transparent text-body-sm text-ds-text-neutral-default-default outline-none placeholder:text-ds-text-neutral-subtle-default",
              backIcon ? "pl-3 pr-9" : "px-3",
            )}
            {...props}
          />
          {backIcon ? (
            <button
              type="button"
              tabIndex={-1}
              className="absolute right-2 inline-flex items-center justify-center rounded-full p-1 text-ds-text-neutral-muted-default hover:bg-ds-bg-neutral-subtle-default"
              onClick={onBackIconClick}
            >
              {backIcon}
            </button>
          ) : null}
        </div>
        {note ? (
          <p
            className={cn(
              "mt-1.5 text-body-sm",
              state === "error"
                ? "text-ds-text-error-default-default"
                : "text-ds-text-neutral-muted-default",
            )}
          >
            {note}
          </p>
        ) : null}
      </div>
    );
  },
);
