/**
 * Adapted from eigent: ChatBox/BottomBox/RichChatInput.tsx
 * Contenteditable input with atomic #skill / @connector chips.
 */
import {
  httpUrlOrNull,
  segmentsToHtml,
  tokenizeRichPlainText,
} from "@/lib/richText";
import { cn } from "@/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export { tokenizeRichPlainText } from "@/lib/richText";

const PLACEHOLDER_ROTATE_MS = 30_000;

function brToNewlineInTree(container: HTMLElement): void {
  container.querySelectorAll("br").forEach((br) => {
    br.replaceWith(document.createTextNode("\n"));
  });
}

function innerPlainFromHtmlTree(container: HTMLElement): string {
  brToNewlineInTree(container);
  // jsdom lacks `innerText`; fall back to textContent for tests.
  const plain = container.innerText ?? container.textContent ?? "";
  return plain.replace(/\u00a0/g, " ");
}

function getPlainTextFromRoot(root: HTMLElement): string {
  const html = root.innerHTML;
  if (!html || html === "<br>" || html === "<br/>" || html === "<br />") {
    return "";
  }
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  return innerPlainFromHtmlTree(tmp);
}

function plainTextLengthBefore(
  root: HTMLElement,
  endContainer: Node,
  endOffset: number,
): number {
  if (!root.contains(endContainer)) return 0;
  const pre = document.createRange();
  pre.selectNodeContents(root);
  pre.setEnd(endContainer, endOffset);
  const tmp = document.createElement("div");
  tmp.appendChild(pre.cloneContents());
  return innerPlainFromHtmlTree(tmp).length;
}

function getCaretOffset(root: HTMLElement): number {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return 0;
  const range = sel.getRangeAt(0);
  return plainTextLengthBefore(root, range.startContainer, range.startOffset);
}

function setCaretOffset(root: HTMLElement, offset: number): void {
  const sel = window.getSelection();
  if (!sel) return;

  const walk = (
    node: Node,
    remaining: { n: number },
  ): { node: Node; offset: number } | null => {
    if (node.nodeType === Node.TEXT_NODE) {
      const len = node.textContent?.length ?? 0;
      if (remaining.n <= len) {
        return { node, offset: remaining.n };
      }
      remaining.n -= len;
      return null;
    }
    if (node.nodeName === "BR") {
      if (remaining.n <= 0) {
        return { node, offset: 0 };
      }
      remaining.n -= 1;
      return null;
    }
    for (let i = 0; i < node.childNodes.length; i++) {
      const found = walk(node.childNodes[i], remaining);
      if (found) return found;
    }
    return null;
  };

  const pos = walk(root, { n: offset });
  if (!pos) {
    const range = document.createRange();
    range.selectNodeContents(root);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
    return;
  }

  const range = document.createRange();
  if (pos.node.nodeType === Node.TEXT_NODE) {
    range.setStart(
      pos.node,
      Math.min(pos.offset, pos.node.textContent?.length ?? 0),
    );
    range.collapse(true);
  } else if (pos.node.nodeName === "BR") {
    range.setStartBefore(pos.node);
    range.collapse(true);
  } else {
    range.selectNodeContents(pos.node);
    range.collapse(false);
  }
  sel.removeAllRanges();
  sel.addRange(range);
}

function scrollCaretIntoView(root: HTMLElement): void {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || !root.contains(sel.anchorNode)) {
    return;
  }
  const range = sel.getRangeAt(0);
  // jsdom Range often lacks layout APIs.
  if (typeof range.getBoundingClientRect !== "function") return;
  let rect = range.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) {
    const rects =
      typeof range.getClientRects === "function" ? range.getClientRects() : [];
    const last = rects[rects.length - 1];
    if (last) rect = last;
  }
  if (rect.width === 0 && rect.height === 0) {
    root.scrollTop = root.scrollHeight - root.clientHeight;
    return;
  }

  const rootRect = root.getBoundingClientRect();
  const padding = 8;
  if (rect.bottom > rootRect.bottom - padding) {
    root.scrollTop += rect.bottom - rootRect.bottom + padding;
  } else if (rect.top < rootRect.top + padding) {
    root.scrollTop += rect.top - rootRect.top - padding;
  }
}

export interface RichChatInputProps {
  value: string;
  onChange: (value: string, cursorOffset?: number) => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLDivElement>) => void;
  onFocus?: () => void;
  onBlur?: () => void;
  onCompositionStart?: () => void;
  onCompositionEnd?: () => void;
  onPasteFiles?: (files: File[]) => void;
  disabled?: boolean;
  placeholder?: string;
  placeholders?: readonly string[];
  className?: string;
  textClassName?: string;
  style?: React.CSSProperties;
  maxHeightPx?: number;
}

export const RichChatInput = React.forwardRef<
  HTMLDivElement,
  RichChatInputProps
>(function RichChatInput(
  {
    value,
    onChange,
    onKeyDown,
    onFocus,
    onBlur,
    onCompositionStart,
    onCompositionEnd,
    onPasteFiles,
    disabled,
    placeholder,
    placeholders: placeholdersProp,
    className,
    textClassName,
    style,
    maxHeightPx = 200,
  },
  ref,
) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const internalUpdate = useRef(false);
  const composingRef = useRef(false);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setRootRef = useCallback(
    (node: HTMLDivElement | null) => {
      rootRef.current = node;
      if (typeof ref === "function") {
        ref(node);
      } else if (ref && "current" in ref) {
        (ref as React.MutableRefObject<HTMLDivElement | null>).current = node;
      }
    },
    [ref],
  );

  const applyHtml = useCallback((plain: string, restoreOffset?: number) => {
    const el = rootRef.current;
    if (!el) return;
    if (plain.length === 0) {
      el.scrollTop = 0;
    }
    const html =
      plain.length === 0 ? "" : segmentsToHtml(tokenizeRichPlainText(plain));
    el.innerHTML = html || "<br />";
    if (restoreOffset !== undefined) {
      setCaretOffset(el, Math.min(restoreOffset, plain.length));
      requestAnimationFrame(() => scrollCaretIntoView(el));
    }
  }, []);

  const resizeHeight = useCallback(() => {
    const el = rootRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, maxHeightPx)}px`;
  }, [maxHeightPx]);

  const handleBlur = useCallback(() => {
    const el = rootRef.current;
    if (!el || composingRef.current) {
      onBlur?.();
      return;
    }
    const plain = getPlainTextFromRoot(el);
    if (plain !== value) {
      internalUpdate.current = true;
      onChange(plain, plain.length);
      applyHtml(plain);
    }
    resizeHeight();
    onBlur?.();
  }, [applyHtml, onBlur, onChange, resizeHeight, value]);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const handleScroll = () => {
      el.classList.add("scrolling");
      if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
      scrollTimeoutRef.current = setTimeout(() => {
        el.classList.remove("scrolling");
      }, 1000);
    };
    el.addEventListener("scroll", handleScroll);
    return () => {
      el.removeEventListener("scroll", handleScroll);
      if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    const el = rootRef.current;
    if (internalUpdate.current) {
      internalUpdate.current = false;
      if (el && getPlainTextFromRoot(el) !== value) {
        applyHtml(value);
      }
      resizeHeight();
      return;
    }
    if (!el) return;
    const current = getPlainTextFromRoot(el);
    if (current === value) {
      if (value === "" && el.innerHTML.replace(/\s/g, "") === "") {
        applyHtml("");
      }
      resizeHeight();
      return;
    }
    const sel = window.getSelection();
    const shouldRestoreCaret =
      document.activeElement === el &&
      sel &&
      sel.rangeCount > 0 &&
      el.contains(sel.anchorNode);
    const caretBefore = shouldRestoreCaret ? getCaretOffset(el) : undefined;
    applyHtml(value, caretBefore);
    resizeHeight();
  }, [value, applyHtml, resizeHeight]);

  const handleInput = () => {
    const el = rootRef.current;
    if (!el || composingRef.current) return;
    const plain = getPlainTextFromRoot(el);
    const caret = getCaretOffset(el);
    internalUpdate.current = true;
    onChange(plain, caret);
    applyHtml(plain, caret);
    resizeHeight();
  };

  const handleChipAwareDelete = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>): boolean => {
      if (e.key !== "Backspace" && e.key !== "Delete") return false;
      const el = rootRef.current;
      if (!el) return false;
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0 || !sel.isCollapsed) return false;

      const caret = getCaretOffset(el);
      const segments = tokenizeRichPlainText(value);
      let offset = 0;
      for (const seg of segments) {
        const start = offset;
        const end = offset + seg.text.length;
        const isChip = seg.type === "skill" || seg.type === "connector";
        const hit =
          isChip &&
          ((e.key === "Backspace" && end === caret) ||
            (e.key === "Delete" && start === caret));
        if (hit) {
          e.preventDefault();
          const newValue = value.slice(0, start) + value.slice(end);
          internalUpdate.current = true;
          onChange(newValue, start);
          applyHtml(newValue, start);
          resizeHeight();
          return true;
        }
        offset = end;
      }
      return false;
    },
    [applyHtml, onChange, resizeHeight, value],
  );

  const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    e.preventDefault();
    const pastedFiles = Array.from(e.clipboardData.items)
      .filter((item) => item.kind === "file")
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null);
    if (pastedFiles.length > 0 && onPasteFiles) {
      onPasteFiles(pastedFiles);
    }
    const text = e.clipboardData.getData("text/plain");
    if (!text) return;
    const el = rootRef.current;
    if (!el) return;
    document.execCommand("insertText", false, text);
  };

  const placeholders = useMemo(() => {
    if (placeholdersProp && placeholdersProp.length > 0) {
      return Array.from(placeholdersProp);
    }
    if (placeholder && placeholder.length > 0) {
      return [placeholder];
    }
    return [];
  }, [placeholdersProp, placeholder]);

  const [isComposing, setIsComposing] = useState(false);
  const showPlaceholder =
    value.length === 0 && !isComposing && placeholders.length > 0;
  const [placeholderCycleIndex, setPlaceholderCycleIndex] = useState(0);

  useEffect(() => {
    setPlaceholderCycleIndex(0);
  }, [placeholders]);

  useEffect(() => {
    if (!showPlaceholder || placeholders.length <= 1) return;
    const id = window.setInterval(() => {
      setPlaceholderCycleIndex((i) => (i + 1) % placeholders.length);
    }, PLACEHOLDER_ROTATE_MS);
    return () => window.clearInterval(id);
  }, [showPlaceholder, placeholders.length]);

  const ariaPlaceholderLine = showPlaceholder
    ? placeholders[placeholderCycleIndex % placeholders.length]
    : undefined;

  return (
    <div className="relative isolate w-full min-w-0 flex-1">
      <div
        aria-hidden
        className="pointer-events-none absolute left-1 top-0 z-[1] w-[calc(100%-0.25rem)] max-w-[calc(100%-0.25rem)] select-none"
      >
        <AnimatePresence mode="wait">
          {showPlaceholder ? (
            <motion.span
              key={placeholders[placeholderCycleIndex % placeholders.length]}
              className="block w-full text-body-sm text-ds-text-neutral-subtle-default"
              initial={{
                opacity: 0,
                filter: "blur(8px)",
                y: -18,
              }}
              animate={{
                opacity: 1,
                filter: "blur(0px)",
                y: 0,
              }}
              exit={{
                opacity: 0,
                filter: "blur(8px)",
                y: 18,
              }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            >
              {placeholders[placeholderCycleIndex % placeholders.length]}
            </motion.span>
          ) : null}
        </AnimatePresence>
      </div>
      <div
        ref={setRootRef}
        role="textbox"
        aria-multiline="true"
        aria-placeholder={ariaPlaceholderLine}
        contentEditable={!disabled}
        suppressContentEditableWarning
        onInput={handleInput}
        onPaste={handlePaste}
        onKeyDown={(e) => {
          if (handleChipAwareDelete(e)) return;
          onKeyDown?.(e);
        }}
        onFocus={onFocus}
        onBlur={handleBlur}
        onCompositionStart={() => {
          composingRef.current = true;
          setIsComposing(true);
          onCompositionStart?.();
        }}
        onCompositionEnd={() => {
          composingRef.current = false;
          setIsComposing(false);
          onCompositionEnd?.();
          handleInput();
        }}
        className={cn(
          "w-full flex-1 resize-none overflow-auto outline-none",
          "scrollbar max-h-[200px] min-h-[40px] py-0 pl-1",
          "relative whitespace-pre-wrap break-words",
          disabled && "cursor-not-allowed opacity-60",
          textClassName,
          className,
        )}
        style={style}
        onMouseDown={(e) => {
          const t = e.target as HTMLElement | null;
          const a = t?.closest(
            'a[data-rich-url="1"]',
          ) as HTMLAnchorElement | null;
          if (a) {
            e.preventDefault();
            const href = a.getAttribute("href");
            const safe = href ? httpUrlOrNull(href) : null;
            if (safe) {
              window.open(safe, "_blank", "noopener,noreferrer");
            }
          }
        }}
      />
    </div>
  );
});

RichChatInput.displayName = "RichChatInput";
