import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useRef } from "react";
import { usePageTabStore } from "@/store/pageTab";
import Settings from "./Settings";

export default function SettingsDialog() {
  const open = usePageTabStore(s => s.settingsOpen);
  const section = usePageTabStore(s => s.settingsSection);
  const setOpen = usePageTabStore(s => s.setSettingsOpen);
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="settings-dialog-overlay" />
        <Dialog.Content
          className="settings-dialog"
          aria-describedby={undefined}
          onOpenAutoFocus={() => { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; }}
          onCloseAutoFocus={event => {
            event.preventDefault();
            if (returnFocus.current?.isConnected) returnFocus.current.focus();
            else document.querySelector<HTMLButtonElement>("[data-settings-trigger]")?.focus();
          }}
        >
          <Dialog.Title className="settings-dialog-title">设置</Dialog.Title>
          <Dialog.Close className="settings-dialog-close" aria-label="关闭设置"><X size={18} aria-hidden /></Dialog.Close>
          <Settings initialTab={section} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
