/**
 * Adapted from eigent: ProjectPageSidebar/SpaceSwitchDropdown.
 * Local Spaces only — no cloud pending-changes submenu.
 */
import {
  Check,
  ChevronDown,
  FolderOpen,
  Pencil,
  Plus,
  PlusCircle,
  Search,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
} from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useCompactLayout } from "@/hooks/useCompactLayout";
import type { CoworkSpace } from "@/store/spaces";

export interface SpaceSwitchDropdownProps {
  trigger?: ReactElement;
  disabled?: boolean;
  spaces: CoworkSpace[];
  activeSpaceId: string | null;
  canRenameActiveSpace?: boolean;
  onRenameSpace: () => void;
  onSpaceSelect: (spaceId: string) => void;
  onStartFromScratch: () => void;
  onSelectFolder: () => void;
  contentAlign?: "start" | "center" | "end";
  contentSide?: "top" | "right" | "bottom" | "left";
  contentClassName?: string;
}

export default function SpaceSwitchDropdown({
  trigger,
  disabled,
  spaces,
  activeSpaceId,
  canRenameActiveSpace = true,
  onRenameSpace,
  onSpaceSelect,
  onStartFromScratch,
  onSelectFolder,
  contentAlign = "start",
  contentSide = "bottom",
  contentClassName,
}: SpaceSwitchDropdownProps) {
  const compact = useCompactLayout();
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const openingDialog = useRef(false);

  const filteredSpaces = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return spaces;
    return spaces.filter((s) => s.name.toLowerCase().includes(q));
  }, [searchQuery, spaces]);

  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => searchInputRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, [open]);

  const handleOpenChange = useCallback((next: boolean) => {
    if (!next) setSearchQuery("");
    setOpen(next);
  }, []);

  const defaultTrigger = (
    <button
      type="button"
      className={cn(
        "flex h-8 w-full min-w-0 items-center justify-between gap-2 rounded-xl px-3 text-left",
        "text-body-sm font-semibold text-ds-text-neutral-muted-default",
        "outline-none hover:bg-ds-bg-neutral-subtle-default",
      )}
      aria-haspopup="menu"
    >
      <span className="min-w-0 flex-1 truncate">
        {spaces.find((s) => s.id === activeSpaceId)?.name || "工作区"}
      </span>
      <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" aria-hidden />
    </button>
  );

  return (
    <DropdownMenu open={open} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild disabled={disabled}>{trigger ?? defaultTrigger}</DropdownMenuTrigger>
      <DropdownMenuContent
        ref={contentRef}
        align={contentAlign}
        side={contentSide}
        sideOffset={6}
        collisionPadding={12}
        onCloseAutoFocus={(event) => {
          if (openingDialog.current) event.preventDefault();
          openingDialog.current = false;
        }}
        className={cn("w-[280px] min-w-0 max-w-[calc(100vw-24px)] overflow-y-auto p-0", contentClassName)}
      >
        <div className="flex flex-col gap-1 p-1">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ds-icon-neutral-muted-default" />
            <input
              ref={searchInputRef}
              value={searchQuery}
              placeholder="搜索工作空间…"
              aria-label="搜索工作空间"
              className="h-8 w-full rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default pl-8 pr-2 text-sm outline-none focus:ring-2 focus:ring-ds-ring-neutral-subtle-default"
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") return;
                e.stopPropagation();
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  contentRef.current?.querySelector<HTMLElement>('[role="menuitem"]:not([data-disabled])')?.focus();
                }
              }}
            />
          </div>

          <div className="max-h-40 overflow-y-auto">
            {filteredSpaces.length === 0 ? (
              <div className="px-2 py-3 text-center text-body-sm text-ds-text-neutral-muted-default">
                无匹配结果
              </div>
            ) : (
              filteredSpaces.map((space) => (
                <DropdownMenuItem
                  key={space.id}
                  className="h-8 cursor-pointer"
                  data-selected={activeSpaceId === space.id}
                  onSelect={() => {
                    onSpaceSelect(space.id);
                    handleOpenChange(false);
                  }}
                >
                  <Check
                    className={cn(
                      "h-4 w-4",
                      activeSpaceId === space.id ? "opacity-100" : "opacity-0",
                    )}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1 truncate">{space.name}</span>
                </DropdownMenuItem>
              ))
            )}
          </div>
        </div>

        <DropdownMenuSeparator className="my-0 bg-ds-border-neutral-default-default" />

        <div className="mb-1 px-1 pt-1">
          <DropdownMenuSub>
            <DropdownMenuSubTrigger className="gap-2 text-ds-text-neutral-default-default">
              <Plus className="h-4 w-4 shrink-0" aria-hidden />
              创建工作空间
            </DropdownMenuSubTrigger>
            <DropdownMenuPortal>
              <DropdownMenuSubContent className="w-52 p-1" sideOffset={compact ? -276 : 6} collisionPadding={12} alignOffset={-4}>
                <DropdownMenuItem
                  className="cursor-pointer gap-2"
                  onSelect={(e) => {
                    e.preventDefault();
                    onStartFromScratch();
                    handleOpenChange(false);
                  }}
                >
                  <PlusCircle className="h-4 w-4 shrink-0" aria-hidden />
                  从空白开始
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="cursor-pointer gap-2"
                  onSelect={(e) => {
                    e.preventDefault();
                    onSelectFolder();
                    handleOpenChange(false);
                  }}
                >
                  <FolderOpen className="h-4 w-4 shrink-0" aria-hidden />
                  选择文件夹…
                </DropdownMenuItem>
              </DropdownMenuSubContent>
            </DropdownMenuPortal>
          </DropdownMenuSub>

          <DropdownMenuItem
            className="cursor-pointer"
            disabled={!canRenameActiveSpace || !activeSpaceId}
            onSelect={() => {
              openingDialog.current = true;
              handleOpenChange(false);
              onRenameSpace();
            }}
          >
            <Pencil className="h-4 w-4" aria-hidden />
            <span>重命名工作空间</span>
          </DropdownMenuItem>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
