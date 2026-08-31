/**
 * Visible agent files (aligned with eigent src/lib/agentFileFilters.ts).
 * Write-tool artifacts show as-is; hide runtime-only dirs and task roots.
 */

type AgentFileLike = {
  path?: string;
  relativePath?: string;
  name?: string;
  source?: string;
  isFolder?: boolean;
};

const RUNTIME_ONLY_DIRS = new Set(["camel_logs", ".venv"]);
const TASK_ROOT_NAME_PATTERN =
  /^task_(?:task_)?(?:\d{10,}(?:-\d+)?|[0-9a-f]{12,}(?:-[0-9a-f]{4,})*)$/i;

function pathSegments(value: string | undefined): string[] {
  return (value || "").replace(/\\/g, "/").split("/").filter(Boolean);
}

function basename(value: string | undefined): string {
  const segments = pathSegments(value);
  return segments[segments.length - 1] || "";
}

export function isRuntimeOnlyAgentFile(file: AgentFileLike): boolean {
  if (file.source === "camel_log") return true;

  const segments = [
    ...pathSegments(file.relativePath),
    ...pathSegments(file.path),
    file.name || "",
  ];

  return segments.some((segment) => RUNTIME_ONLY_DIRS.has(segment));
}

export function isAgentTaskRootEntry(file: AgentFileLike): boolean {
  const name = file.name || basename(file.path);
  if (!TASK_ROOT_NAME_PATTERN.test(name)) return false;

  const relativeSegments = pathSegments(file.relativePath);
  if (relativeSegments.length === 0) return basename(file.path) === name;

  return relativeSegments.length === 1 && relativeSegments[0] === name;
}

export function isVisibleAgentFile(file: AgentFileLike): boolean {
  return (
    !file.isFolder &&
    !isRuntimeOnlyAgentFile(file) &&
    !isAgentTaskRootEntry(file)
  );
}

export function isVisibleAgentPath(filePath: string): boolean {
  return isVisibleAgentFile({ path: filePath });
}

/** Image files that should not auto-open as mid-run preview tabs. */
export function isPreviewImagePath(filePath: string): boolean {
  return /\.(png|jpe?g|webp|gif|svg|bmp)$/i.test(filePath.replace(/\\/g, "/"));
}

/** Helper scripts (e.g. `_gen_*.py`) are not chat/work-log deliverables. */
export function isProcessCodePath(filePath: string): boolean {
  return /\.(py|pyw|sh|bash|zsh|ps1|js|mjs|cjs|ts|tsx)$/i.test(
    basename(filePath),
  );
}
