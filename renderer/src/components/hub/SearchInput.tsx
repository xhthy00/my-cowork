/**
 * Adapted from eigent: src/components/Dashboard/SearchInput
 * Icon variant expands 28→240 on click; default is a full-width field.
 */
import { AnimatePresence, motion } from "framer-motion";
import { Search, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type SearchInputVariant = "default" | "icon";

interface SearchInputProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  variant?: SearchInputVariant;
  onSearch?: () => void;
}

const COLLAPSED_WIDTH = 28;
const EXPANDED_WIDTH = 240;

export default function SearchInput({
  value,
  onChange,
  placeholder = "搜索…",
  variant = "default",
  onSearch,
}: SearchInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [userExpanded, setUserExpanded] = useState(false);
  const isExpanded = userExpanded || value.length > 0;

  const expand = useCallback(() => setUserExpanded(true), []);
  const collapse = useCallback(() => {
    setUserExpanded(false);
    onChange({ target: { value: "" } } as React.ChangeEvent<HTMLInputElement>);
  }, [onChange]);

  useEffect(() => {
    if (!userExpanded) return;
    const id = setTimeout(() => inputRef.current?.focus(), 150);
    return () => clearTimeout(id);
  }, [userExpanded]);

  if (variant === "icon") {
    return (
      <motion.div
        className={cn(
          "flex items-center justify-center overflow-hidden rounded-lg border border-solid border-transparent bg-transparent py-0.5",
          "hover:bg-ds-bg-neutral-strong-default focus-within:bg-ds-bg-neutral-strong-default",
        )}
        initial={false}
        animate={{ width: isExpanded ? EXPANDED_WIDTH : COLLAPSED_WIDTH }}
        transition={{ type: "spring", stiffness: 400, damping: 30 }}
      >
        <AnimatePresence mode="wait">
          {!isExpanded ? (
            <motion.div
              key="icon"
              className="flex shrink-0 items-center justify-center"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={expand}
                aria-label="搜索"
                title="搜索"
              >
                <Search className="h-4 w-4" />
              </Button>
            </motion.div>
          ) : (
            <motion.div
              key="input"
              className="flex min-w-0 flex-1 items-center gap-0 pr-1"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              <span className="pointer-events-none ml-2 inline-flex h-4 w-4 shrink-0 items-center justify-center text-ds-icon-neutral-muted-default">
                <Search className="h-4 w-4" />
              </span>
              <input
                ref={inputRef}
                type="text"
                value={value}
                onChange={onChange}
                placeholder={placeholder}
                onBlur={() => {
                  if (value.length === 0) setUserExpanded(false);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSearch?.();
                }}
                className="h-6 min-w-0 flex-1 bg-transparent pl-2 text-xs text-ds-text-neutral-default-default outline-none placeholder:text-ds-text-neutral-muted-default"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 rounded-full"
                onClick={collapse}
                aria-label="清除"
                title="清除"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    );
  }

  return (
    <div className="relative w-full">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ds-text-neutral-subtle-default" />
      <input
        className="h-8 w-full rounded-lg border border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default pl-8 pr-2 text-xs outline-none"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        onKeyDown={(e) => {
          if (e.key === "Enter") onSearch?.();
        }}
      />
    </div>
  );
}
