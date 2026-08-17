/**
 * Adapted from eigent: src/components/ui/tabs.tsx
 * Supports appearance: default | border | ghost (Hub Skills / VerticalNav).
 */
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { motion, useReducedMotion } from "framer-motion";
import * as React from "react";

import { cn } from "@/lib/utils";

export type TabsAppearance = "default" | "border" | "ghost";

const TabsContext = React.createContext<{ appearance?: TabsAppearance }>({
  appearance: "default",
});

export const Tabs = TabsPrimitive.Root;

type TabsListProps = React.ComponentPropsWithoutRef<typeof TabsPrimitive.List> & {
  appearance?: TabsAppearance;
};

export const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  TabsListProps
>(({ className, appearance = "default", ...props }, ref) => {
  const reduceMotion = useReducedMotion() === true;
  const listRef = React.useRef<HTMLDivElement | null>(null);
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const [bar, setBar] = React.useState({ left: 0, top: 0, width: 0 });

  React.useLayoutEffect(() => {
    if (appearance !== "border") return;
    const update = () => {
      const list = listRef.current;
      const wrap = wrapRef.current;
      if (!list || !wrap) return;
      const active = list.querySelector(
        '[data-state="active"][data-tabs-appearance="border"]',
      ) as HTMLElement | null;
      if (!active) return;
      const wr = wrap.getBoundingClientRect();
      const tr = active.getBoundingClientRect();
      setBar({
        left: tr.left - wr.left,
        top: tr.bottom - wr.top + 8,
        width: tr.width,
      });
    };
    update();
    const mo = new MutationObserver(update);
    if (listRef.current) {
      mo.observe(listRef.current, {
        attributes: true,
        attributeFilter: ["data-state"],
        subtree: true,
      });
    }
    window.addEventListener("resize", update);
    return () => {
      mo.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [appearance]);

  const setRefs = React.useCallback(
    (node: HTMLDivElement | null) => {
      listRef.current = node;
      if (typeof ref === "function") ref(node);
      else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = node;
    },
    [ref],
  );

  return (
    <TabsContext.Provider value={{ appearance }}>
      <div ref={wrapRef} className={cn("relative", appearance === "border" && "pb-2")}>
        <TabsPrimitive.List
          ref={setRefs}
          data-tabs-appearance={appearance}
          className={cn(
            "inline-flex items-center justify-center",
            appearance === "default" &&
              "h-9 gap-0.5 rounded-xl bg-ds-bg-neutral-strong-default p-0.5 text-ds-text-neutral-muted-default",
            appearance === "border" &&
              "h-auto flex-1 justify-start gap-2 rounded-none border-0 bg-transparent p-0 shadow-none",
            appearance === "ghost" &&
              "h-auto w-full flex-col items-stretch gap-1.5 rounded-none border-0 bg-transparent p-0 shadow-none",
            className,
          )}
          {...props}
        />
        {appearance === "border" && bar.width > 0 && (
          <motion.div
            aria-hidden
            className="pointer-events-none absolute z-10 h-0.5 rounded-full bg-ds-bg-brand-default-default"
            initial={false}
            animate={{ left: bar.left, top: bar.top, width: bar.width }}
            transition={
              reduceMotion
                ? { duration: 0 }
                : { type: "spring", stiffness: 420, damping: 34, mass: 0.55 }
            }
          />
        )}
      </div>
    </TabsContext.Provider>
  );
});
TabsList.displayName = TabsPrimitive.List.displayName;

type TabsTriggerProps = React.ComponentPropsWithoutRef<
  typeof TabsPrimitive.Trigger
> & {
  appearance?: TabsAppearance;
};

export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  TabsTriggerProps
>(({ className, appearance: appearanceProp, ...props }, ref) => {
  const { appearance: ctx } = React.useContext(TabsContext);
  const appearance = appearanceProp ?? ctx ?? "default";
  return (
    <TabsPrimitive.Trigger
      ref={ref}
      data-tabs-appearance={appearance}
      className={cn(
        appearance === "default" &&
          "inline-flex items-center justify-center gap-1 whitespace-nowrap rounded-xl px-2.5 py-1 text-body-sm font-semibold transition-all data-[state=active]:bg-ds-bg-neutral-subtle-default data-[state=active]:text-ds-text-neutral-default-default data-[state=active]:shadow-sm",
        appearance === "border" &&
          "inline-flex h-8 min-h-8 shrink-0 items-center justify-center gap-1 whitespace-nowrap rounded-lg border border-transparent bg-transparent px-2 text-label-sm font-bold text-ds-text-neutral-muted-default transition-colors hover:bg-ds-bg-neutral-subtle-default hover:text-ds-text-neutral-default-default data-[state=active]:bg-transparent data-[state=active]:text-ds-text-neutral-default-default data-[state=active]:shadow-none",
        appearance === "ghost" &&
          "inline-flex w-full items-center justify-start gap-2 rounded-xl border-0 bg-transparent px-3 py-1.5 text-body-sm font-semibold text-ds-text-neutral-muted-default shadow-none transition-colors data-[state=inactive]:opacity-70 data-[state=inactive]:hover:bg-ds-bg-neutral-default-hover data-[state=inactive]:hover:opacity-100 data-[state=active]:bg-ds-bg-neutral-default-default data-[state=active]:text-ds-text-neutral-default-default data-[state=active]:opacity-100",
        className,
      )}
      {...props}
    />
  );
});
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

export const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content ref={ref} className={cn("mt-2 outline-none", className)} {...props} />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;
