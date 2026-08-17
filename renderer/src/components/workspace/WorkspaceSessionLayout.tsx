/**
 * Adapted from eigent: Session/index.tsx — chat ↔ preview drag resize.
 * Layout: Chat | [handle] Preview | SidePanel
 *
 * The chat column width is freely draggable between CHAT_MIN_WIDTH and
 * "all space minus the preview minimum" (scales with window size), persists
 * across restarts, and double-clicking the handle resets to the default.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";
import { usePageTabStore } from "@/store/pageTab";
import { usePreviewStore } from "@/store/preview";

/** Default width the chat column starts with while display is open. */
const CHAT_DEFAULT_WIDTH = 680;
/** Smallest the chat column may be dragged to. */
const CHAT_MIN_WIDTH = 360;
/** Keep at least this much room for the preview when the chat is widened. */
const PREVIEW_MIN_WIDTH = 320;
const CHAT_WIDTH_STORAGE_KEY = "my-cowork-chat-preview-width";

function loadSavedChatWidth(): number | null {
  try {
    const raw = window.localStorage.getItem(CHAT_WIDTH_STORAGE_KEY);
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) && value >= CHAT_MIN_WIDTH ? value : null;
  } catch {
    return null;
  }
}

function saveChatWidth(width: number): void {
  try {
    window.localStorage.setItem(CHAT_WIDTH_STORAGE_KEY, String(Math.round(width)));
  } catch {
    // Storage unavailable — width just won't persist.
  }
}

function ResizeHandle({
  active,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onDoubleClick,
}: {
  active: boolean;
  onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerUp: (e: React.PointerEvent<HTMLDivElement>) => void;
  onDoubleClick: () => void;
}) {
  return (
    <div
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onLostPointerCapture={onPointerUp}
      onDoubleClick={onDoubleClick}
      role="separator"
      aria-orientation="vertical"
      title="拖动调整宽度，双击重置"
      data-resize-handle-state={active ? "drag" : "inactive"}
      className={cn(
        "relative z-10 flex w-[2px] shrink-0 cursor-col-resize items-center justify-center bg-transparent transition-colors hover:bg-ds-bg-brand-subtle-default",
        "before:absolute before:inset-y-0 before:-left-1 before:-right-1 before:content-['']",
        "after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2 after:bg-ds-bg-neutral-default-default after:transition-colors",
        active &&
          "bg-ds-bg-brand-subtle-default after:bg-ds-bg-brand-default-focus",
      )}
    />
  );
}

export default function WorkspaceSessionLayout({
  chat,
  preview,
  side,
}: {
  chat: ReactNode;
  preview: ReactNode;
  side: ReactNode;
}) {
  const pagePreviewOpen = usePageTabStore((s) => s.previewOpen);
  const storeOpen = usePreviewStore((s) => s.open);
  const previewOpen = pagePreviewOpen && storeOpen;

  const rowRef = useRef<HTMLDivElement>(null);
  const userChatWidthRef = useRef<number | null>(null);
  const dragStartRef = useRef<{ x: number; width: number } | null>(null);
  const [chatWidth, setChatWidth] = useState(
    () => loadSavedChatWidth() ?? CHAT_DEFAULT_WIDTH,
  );
  const [isResizing, setIsResizing] = useState(false);

  /** Widest the chat may grow given the current window/panel geometry. */
  const computeMaxChat = useCallback(() => {
    const rowWidth =
      rowRef.current?.getBoundingClientRect().width ?? window.innerWidth;
    const sidePanelWidth =
      document.getElementById("session-side-panel")?.getBoundingClientRect()
        .width ?? 0;
    return Math.max(CHAT_MIN_WIDTH, rowWidth - sidePanelWidth - PREVIEW_MIN_WIDTH);
  }, []);

  useEffect(() => {
    if (previewOpen) {
      const desired =
        userChatWidthRef.current ?? loadSavedChatWidth() ?? CHAT_DEFAULT_WIDTH;
      setChatWidth(Math.min(Math.max(desired, CHAT_MIN_WIDTH), computeMaxChat()));
    }
  }, [previewOpen, computeMaxChat]);

  // Re-clamp on window/panel resize so the fixed-width chat column never
  // overflows the row (which overflow-hidden would clip from the right).
  useEffect(() => {
    if (!previewOpen) return;
    const onResize = () => {
      setChatWidth((w) =>
        Math.min(Math.max(w, CHAT_MIN_WIDTH), computeMaxChat()),
      );
    };
    window.addEventListener("resize", onResize);
    const ro =
      typeof ResizeObserver !== "undefined" && rowRef.current
        ? new ResizeObserver(onResize)
        : null;
    if (ro && rowRef.current) ro.observe(rowRef.current);
    return () => {
      window.removeEventListener("resize", onResize);
      ro?.disconnect();
    };
  }, [previewOpen, computeMaxChat]);

  const handlePreviewResizeStart = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      // Capture keeps the drag alive even when the pointer leaves the window.
      e.currentTarget.setPointerCapture(e.pointerId);
      dragStartRef.current = { x: e.clientX, width: chatWidth };
      setIsResizing(true);
    },
    [chatWidth],
  );

  const handlePreviewResizeMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const start = dragStartRef.current;
      if (!start) return;
      const next = Math.min(
        computeMaxChat(),
        Math.max(CHAT_MIN_WIDTH, start.width + (e.clientX - start.x)),
      );
      userChatWidthRef.current = next;
      setChatWidth(next);
    },
    [computeMaxChat],
  );

  const handlePreviewResizeEnd = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!dragStartRef.current) return;
      dragStartRef.current = null;
      setIsResizing(false);
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
      if (userChatWidthRef.current != null) {
        saveChatWidth(userChatWidthRef.current);
      }
    },
    [],
  );

  const handlePreviewResizeReset = useCallback(() => {
    userChatWidthRef.current = CHAT_DEFAULT_WIDTH;
    setChatWidth(CHAT_DEFAULT_WIDTH);
    saveChatWidth(CHAT_DEFAULT_WIDTH);
  }, []);

  return (
    <div
      ref={rowRef}
      className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-row overflow-hidden"
    >
      <div
        style={previewOpen ? { width: chatWidth } : undefined}
        className={cn(
          "flex min-h-0 min-w-0 flex-col overflow-hidden",
          previewOpen ? "shrink-0" : "flex-1",
          !isResizing && "transition-[width] duration-200 ease-out",
        )}
      >
        {chat}
      </div>

      {previewOpen ? (
        <>
          <ResizeHandle
            active={isResizing}
            onPointerDown={handlePreviewResizeStart}
            onPointerMove={handlePreviewResizeMove}
            onPointerUp={handlePreviewResizeEnd}
            onDoubleClick={handlePreviewResizeReset}
          />
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
            {preview}
          </div>
        </>
      ) : null}

      <div
        id="session-side-panel"
        className="flex min-h-0 shrink-0 flex-col overflow-hidden"
      >
        {side}
      </div>
    </div>
  );
}
