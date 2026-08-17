/**
 * Colored file-type glyph for artifact chips / side panel / work log.
 * Visual language: rounded square badge + Lucide glyph (screenshot-aligned).
 */
import type { LucideIcon } from "lucide-react";
import {
  File,
  FileArchive,
  FileCode2,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileType2,
  Presentation,
} from "lucide-react";

import { fileBasename } from "@/lib/fsPath";
import { cn } from "@/lib/utils";

export type FileTypeKind =
  | "docx"
  | "xlsx"
  | "pptx"
  | "pdf"
  | "md"
  | "txt"
  | "image"
  | "code"
  | "archive"
  | "file";

export function extOfPath(pathOrName: string): string {
  const base = fileBasename(pathOrName) || pathOrName;
  const i = base.lastIndexOf(".");
  return i >= 0 ? base.slice(i + 1).toLowerCase() : "";
}

export function fileTypeKind(pathOrName: string, hint?: string): FileTypeKind {
  const ext = extOfPath(pathOrName) || (hint || "").toLowerCase();
  if (ext === "docx" || ext === "doc" || ext === "rtf" || hint === "docx") return "docx";
  if (ext === "xlsx" || ext === "xls" || ext === "csv" || hint === "xlsx") return "xlsx";
  if (ext === "pptx" || ext === "ppt" || hint === "pptx") return "pptx";
  if (ext === "pdf" || hint === "pdf") return "pdf";
  if (ext === "md" || ext === "markdown") return "md";
  if (ext === "txt" || ext === "log") return "txt";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "heic"].includes(ext)) {
    return "image";
  }
  if (
    ["py", "js", "ts", "tsx", "jsx", "json", "yml", "yaml", "toml", "sh", "bash", "css", "html"].includes(
      ext,
    )
  ) {
    return "code";
  }
  if (["zip", "tar", "gz", "tgz", "rar", "7z"].includes(ext)) return "archive";
  return "file";
}

const KIND_META: Record<
  FileTypeKind,
  { Icon: LucideIcon; badge: string; glyph: string; label: string }
> = {
  docx: {
    Icon: FileText,
    badge: "bg-[#2b7fff]",
    glyph: "text-white",
    label: "Word",
  },
  xlsx: {
    Icon: FileSpreadsheet,
    badge: "bg-[#00a63e]",
    glyph: "text-white",
    label: "Excel",
  },
  pptx: {
    Icon: Presentation,
    badge: "bg-[#e17100]",
    glyph: "text-white",
    label: "PPT",
  },
  pdf: {
    Icon: FileType2,
    badge: "bg-[#e7000b]",
    glyph: "text-white",
    label: "PDF",
  },
  md: {
    Icon: FileCode2,
    badge: "bg-[#535352]",
    glyph: "text-white",
    label: "Markdown",
  },
  txt: {
    Icon: FileText,
    badge: "bg-[#757473]",
    glyph: "text-white",
    label: "Text",
  },
  image: {
    Icon: FileImage,
    badge: "bg-[#7c3aed]",
    glyph: "text-white",
    label: "Image",
  },
  code: {
    Icon: FileCode2,
    badge: "bg-[#0d9488]",
    glyph: "text-white",
    label: "Code",
  },
  archive: {
    Icon: FileArchive,
    badge: "bg-[#a16207]",
    glyph: "text-white",
    label: "Archive",
  },
  file: {
    Icon: File,
    badge: "bg-[#aaaaaa]",
    glyph: "text-white",
    label: "File",
  },
};

export function fileTypeMeta(pathOrName: string, hint?: string) {
  return KIND_META[fileTypeKind(pathOrName, hint)];
}

interface FileTypeIconProps {
  pathOrName: string;
  /** Optional FileArtifact.kind / extension hint */
  hint?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE: Record<NonNullable<FileTypeIconProps["size"]>, { box: string; icon: string }> = {
  sm: { box: "h-6 w-6 rounded-md", icon: "h-3.5 w-3.5" },
  md: { box: "h-8 w-8 rounded-lg", icon: "h-4 w-4" },
  lg: { box: "h-10 w-10 rounded-xl", icon: "h-5 w-5" },
};

export default function FileTypeIcon({
  pathOrName,
  hint,
  size = "md",
  className,
}: FileTypeIconProps) {
  const meta = fileTypeMeta(pathOrName, hint);
  const dim = SIZE[size];
  const Icon = meta.Icon;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center",
        dim.box,
        meta.badge,
        className,
      )}
      title={meta.label}
      aria-hidden
    >
      <Icon className={cn(dim.icon, meta.glyph)} strokeWidth={2} />
    </span>
  );
}
