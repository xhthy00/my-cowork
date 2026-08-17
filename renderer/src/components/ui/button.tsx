/**
 * Adapted from eigent: src/components/ui/button.tsx (neutral primary subset).
 * Keeps Hub-critical variants/sizes without the full tone matrix.
 */
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center whitespace-nowrap border border-solid",
    "transition-[background-color,border-color,color,box-shadow,opacity,transform]",
    "duration-[160ms] ease-[cubic-bezier(0.23,1,0.32,1)] active:scale-[0.97] motion-reduce:transform-none motion-reduce:active:scale-100",
    "disabled:pointer-events-none disabled:opacity-50",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:!text-inherit",
    "outline-none focus-visible:ring-2 focus-visible:ring-ds-ring-neutral-subtle-default focus-visible:ring-offset-2",
    "shrink-0 cursor-pointer",
  ].join(" "),
  {
    variants: {
      variant: {
        /* !text/!bg: beat any leftover unlayered button resets (Eigent uses !text-*) */
        primary: [
          "!bg-ds-bg-brand-default-default !border-ds-bg-brand-default-default",
          "!text-ds-text-brand-inverse-default shadow-button",
          "hover:!bg-ds-text-brand-strong-default hover:!border-ds-text-brand-strong-default",
        ].join(" "),
        secondary: [
          "!bg-ds-bg-neutral-subtle-default !border-ds-bg-neutral-subtle-default",
          "!text-ds-text-neutral-default-default shadow-button",
          "hover:!bg-ds-bg-neutral-strong-default hover:!border-ds-bg-neutral-strong-default",
        ].join(" "),
        outline: [
          "!bg-transparent !border-ds-border-neutral-strong-default",
          "!text-ds-text-neutral-default-default shadow-button",
          "hover:!bg-ds-bg-neutral-subtle-default",
        ].join(" "),
        ghost: [
          "!bg-transparent !border-transparent !text-ds-text-neutral-default-default",
          "hover:!bg-ds-bg-neutral-default-hover",
        ].join(" "),
        destructive: [
          "!bg-[var(--danger)] !border-[var(--danger)] !text-white shadow-button",
          "hover:opacity-90",
        ].join(" "),
      },
      size: {
        xs: "box-border min-h-6 !rounded-md px-1.5 py-0 text-label-xs font-bold [&_svg:not([class*='size-'])]:size-[14px]",
        sm: "box-border min-h-[28px] !rounded-lg px-2 py-0 text-label-sm font-medium [&_svg:not([class*='size-'])]:size-4 gap-1",
        default:
          "box-border min-h-8 !rounded-lg px-4 py-0 text-label-sm font-medium [&_svg:not([class*='size-'])]:size-4 gap-2",
        lg: "box-border min-h-9 !rounded-lg px-4 py-0 text-sm font-bold [&_svg:not([class*='size-'])]:size-5 gap-2",
        icon: "box-border h-7 w-7 min-h-7 min-w-7 !rounded-md p-1.5 [&_svg:not([class*='size-'])]:size-4",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size }), className)}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
