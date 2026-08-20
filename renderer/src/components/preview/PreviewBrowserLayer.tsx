/**
 * Adapted from eigent: PreviewBrowserLayer.tsx + webviewRegistry.ts
 * Always-mounted webviews; inactive tabs park off-screen to preserve history.
 */
import { useEffect, useRef } from "react";

import { usePreviewStore, type SessionBrowserTab } from "../../store/preview";

const registry = new Map<string, HTMLElement>();

export function registerPreviewWebview(id: string, el: HTMLElement) {
  registry.set(id, el);
}

export function unregisterPreviewWebview(id: string) {
  registry.delete(id);
}

export function getPreviewWebview(id: string): HTMLElement | undefined {
  return registry.get(id);
}

function BrowserWebview({
  tab,
  active,
}: {
  tab: SessionBrowserTab;
  active: boolean;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const updateBrowserNav = usePreviewStore((s) => s.updateBrowserNav);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    // Prefer Electron <webview>; fall back to iframe in browser/dev.
    const isElectron = !!(window as unknown as { process?: { versions?: { electron?: string } } })
      .process?.versions?.electron
      || navigator.userAgent.includes("Electron");

    let el: HTMLElement;
    if (isElectron) {
      el = document.createElement("webview");
      el.setAttribute("src", tab.url);
      el.setAttribute("partition", "persist:session-preview");
      el.setAttribute("allowpopups", "true");
      // Local HTML deliverables need file:// (scripts / relative assets).
      if (tab.url.startsWith("file://") || tab.url.startsWith("localfile://")) {
        el.setAttribute(
          "webpreferences",
          "webSecurity=no, allowRunningInsecureContent",
        );
      }
      el.style.cssText =
        "position:absolute;inset:0;width:100%;height:100%;border:none;display:flex;";

      const onNav = () => {
        const wv = el as HTMLElement & {
          getURL?: () => string;
          getTitle?: () => string;
          isLoading?: () => boolean;
          canGoBack?: () => boolean;
          canGoForward?: () => boolean;
        };
        updateBrowserNav(tab.id, {
          url: wv.getURL?.() || tab.url,
          title: wv.getTitle?.() || tab.title,
          isLoading: Boolean(wv.isLoading?.()),
          canGoBack: Boolean(wv.canGoBack?.()),
          canGoForward: Boolean(wv.canGoForward?.()),
        });
      };
      el.addEventListener("did-navigate", onNav);
      el.addEventListener("did-navigate-in-page", onNav);
      el.addEventListener("did-stop-loading", onNav);
      el.addEventListener("page-title-updated", onNav);
    } else {
      el = document.createElement("iframe");
      (el as HTMLIFrameElement).src = tab.navigation.url || tab.url;
      el.style.cssText =
        "position:absolute;inset:0;width:100%;height:100%;border:none;display:block;";
    }

    host.appendChild(el);
    registerPreviewWebview(tab.webviewId, el);

    return () => {
      unregisterPreviewWebview(tab.webviewId);
      host.replaceChildren();
    };
    // Mount once per tab id; URL updates are handled via webview/iframe navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab.id, tab.webviewId]);

  useEffect(() => {
    const el = getPreviewWebview(tab.webviewId) as
      | (HTMLElement & { loadURL?: (u: string) => void })
      | undefined;
    if (!el) return;
    const next = tab.navigation.url || tab.url;
    if (el.tagName.toLowerCase() === "webview" && el.loadURL) {
      try {
        const current = (el as { getURL?: () => string }).getURL?.();
        if (current && current !== next) el.loadURL(next);
      } catch {
        /* guest may not be ready */
      }
    } else if (el.tagName.toLowerCase() === "iframe") {
      const iframe = el as HTMLIFrameElement;
      if (iframe.src !== next) iframe.src = next;
    }
  }, [tab.navigation.url, tab.url, tab.webviewId]);

  return (
    <div
      ref={hostRef}
      className={`preview-webview-layer ${active ? "shown" : "parked"}`}
      data-webview-id={tab.webviewId}
    />
  );
}

/** Persistent layer for all browser tabs in the session. */
export function PreviewBrowserLayer() {
  const tabs = usePreviewStore((s) => s.tabs);
  const activeTabId = usePreviewStore((s) => s.activeTabId);
  const open = usePreviewStore((s) => s.open);
  const browsers = tabs.filter((t): t is SessionBrowserTab => t.type === "browser");

  if (!browsers.length) return null;

  return (
    <div className="preview-browser-layer" aria-hidden={!open}>
      {browsers.map((tab) => (
        <BrowserWebview
          key={tab.id}
          tab={tab}
          active={open && tab.id === activeTabId}
        />
      ))}
    </div>
  );
}

export default PreviewBrowserLayer;
