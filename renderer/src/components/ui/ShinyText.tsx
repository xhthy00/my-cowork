/**
 * Adapted from eigent: components/ui/ShinyText — live “in progress” indicator.
 */
import { cn } from "@/lib/utils";

export default function ShinyText({
  text,
  disabled = false,
  speed = 2.5,
  className,
}: {
  text: string;
  disabled?: boolean;
  speed?: number;
  className?: string;
}) {
  return (
    <span
      className={cn("shiny-text", disabled && "disabled", className)}
      style={{ animationDuration: `${speed}s` }}
    >
      {text}
    </span>
  );
}
