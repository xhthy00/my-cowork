import * as Dialog from "@radix-ui/react-dialog";
import { ChevronDown, Folder } from "lucide-react";
import { useRef, useState } from "react";

import SpaceSwitchDropdown from "@/components/shell/SpaceSwitchDropdown";
import { Button } from "@/components/ui/button";
import { ensureActiveSession, useSessionsStore } from "@/store/sessions";
import { useSpacesStore } from "@/store/spaces";

/** Workspace management lives with the composer that will use the selected space. */
export default function ChatSpaceSelect({
  draft,
  disabled,
}: {
  draft: boolean;
  disabled?: boolean;
}) {
  const spaces = useSpacesStore(s => s.spaces);
  const activeSpaceId = useSpacesStore(s => s.activeSpaceId);
  const projectSpaceId = useSessionsStore(s => s.sessions.find(p => p.id === s.activeId)?.spaceId);
  const selectedSpaceId = projectSpaceId || activeSpaceId;
  const selectedSpace = spaces.find(space => space.id === selectedSpaceId);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [pickingFolder, setPickingFolder] = useState(false);
  const [folderError, setFolderError] = useState("");

  function selectSpace(spaceId: string, created = false) {
    const spaceStore = useSpacesStore.getState();
    if (!spaceStore.spaces.some(space => space.id === spaceId)) return;
    spaceStore.setActiveSpace(spaceId);
    const sessions = useSessionsStore.getState();
    if (draft) {
      // Keep the text, attachments and assistant binding of an unsent draft.
      sessions.touchSession(ensureActiveSession(), {
        spaceId,
        workdirMode: spaceStore.defaultWorkdirMode(spaceId),
      });
    } else if (spaceId !== selectedSpaceId) {
      // Never move an existing conversation's messages or output directory.
      const first = created ? undefined : sessions.projectsForSpace(spaceId)[0];
      if (first) sessions.setActive(first.id);
      else sessions.createProject("新对话", { spaceId });
    }
  }

  async function pickFolder() {
    const projectId = useSessionsStore.getState().activeId;
    setPickingFolder(true);
    setFolderError("");
    try {
      const path = await window.api.selectDirectory?.();
      if (!path || projectId !== useSessionsStore.getState().activeId) return;
      const name = path.split(/[/\\]/).filter(Boolean).pop() || "文件夹工作区";
      selectSpace(useSpacesStore.getState().createFolderSpace(name, path), true);
    } catch {
      setFolderError("无法打开文件夹选择，请重试。");
    } finally {
      setPickingFolder(false);
    }
  }

  function saveName() {
    const name = renameValue.trim();
    if (!name || !renameTarget) return;
    useSpacesStore.getState().renameSpace(renameTarget, name);
    setRenameTarget(null);
  }

  return <>
    <SpaceSwitchDropdown
      disabled={disabled || pickingFolder}
      spaces={spaces}
      activeSpaceId={selectedSpaceId}
      canRenameActiveSpace={Boolean(selectedSpace)}
      contentSide="top"
      contentClassName="chat-space-menu"
      trigger={<button
        ref={triggerRef}
        type="button"
        className="chat-space-select"
        aria-label="选择工作空间"
        title={selectedSpace?.name || "选择工作空间"}
        disabled={disabled || pickingFolder}
      >
        <Folder size={16} aria-hidden />
        <span>{selectedSpace?.name || "选择工作空间"}</span>
        <ChevronDown size={13} aria-hidden />
      </button>}
      onSpaceSelect={selectSpace}
      onStartFromScratch={() => selectSpace(useSpacesStore.getState().createBlankSpace(), true)}
      onSelectFolder={() => void pickFolder()}
      onRenameSpace={() => {
        if (!selectedSpace) return;
        setRenameValue(selectedSpace.name);
        setRenameTarget(selectedSpace.id);
      }}
    />
    {folderError && <span role="alert" className="text-xs text-ds-text-danger-default-default">{folderError}</span>}
    <Dialog.Root open={Boolean(renameTarget)} onOpenChange={open => { if (!open) setRenameTarget(null); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[100] bg-black/30" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-[101] w-[calc(100vw-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default p-5 shadow-lg"
          onCloseAutoFocus={event => { event.preventDefault(); triggerRef.current?.focus(); }}
        >
          <Dialog.Title className="mb-3 text-base font-semibold">重命名工作空间</Dialog.Title>
          <form onSubmit={event => { event.preventDefault(); saveName(); }}>
            <input
              autoFocus
              aria-label="工作空间名称"
              value={renameValue}
              className="h-9 w-full rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-3 text-sm"
              onChange={event => setRenameValue(event.target.value)}
            />
            <div className="mt-5 flex justify-end gap-2">
              <Dialog.Close asChild><Button type="button" variant="ghost">取消</Button></Dialog.Close>
              <Button type="submit" disabled={!renameValue.trim()}>保存</Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  </>;
}
