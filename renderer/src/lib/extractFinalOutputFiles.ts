/**
 * Copied from eigent src/store/chatStore.ts
 * extractFinalOutputFileList / mergeFileInfoLists.
 *
 * At task end, scrape absolute paths from the summary and merge with files
 * already recorded from WRITE_FILE / artifact.file. Do not create files.
 */

export type ExtractedOutputFile = {
  name: string;
  path: string;
  kind: "pptx" | "docx" | "xlsx" | "pdf" | "file";
};

const FINAL_OUTPUT_FILE_PATH_REGEX =
  /(?<![A-Za-z0-9:\\/])(?:[A-Za-z]:)?[\\/][^\s`"'<>|*]+?\.[A-Za-z0-9]{1,12}(?=$|[\s`"'<>|*),;:\]}])/g;

const FINAL_OUTPUT_SANDBOX_SCHEME_REGEX =
  /(^|[^A-Za-z0-9_+.-])sandbox:(?=(?:[A-Za-z]:)?[\\/])/gi;

const FINAL_OUTPUT_FILE_EXTENSIONS = new Set([
  "csv",
  "doc",
  "docx",
  "gif",
  "htm",
  "html",
  "jpeg",
  "jpg",
  "json",
  "log",
  "md",
  "pdf",
  "png",
  "ppt",
  "pptx",
  "svg",
  "tsv",
  "txt",
  "webp",
  "xls",
  "xlsx",
  "xml",
  "zip",
]);

function normalizeOutputPath(path: string): string {
  return path.replace(/\\/g, "/").trim();
}

function getOutputFileNameFromPath(path: string): string {
  return normalizeOutputPath(path).split("/").pop() || "";
}

function getFileTypeFromName(name: string): string {
  const extension = name.split(".").pop()?.toLowerCase() || "";
  return extension === name.toLowerCase() ? "" : extension;
}

function artifactKind(type: string): ExtractedOutputFile["kind"] {
  if (type === "pptx" || type === "ppt") return "pptx";
  if (type === "docx" || type === "doc") return "docx";
  if (type === "xlsx" || type === "xls") return "xlsx";
  if (type === "pdf") return "pdf";
  return "file";
}

export function extractFinalOutputFileList(content: string): ExtractedOutputFile[] {
  if (!content) return [];

  const fileInfos: ExtractedOutputFile[] = [];
  const seen = new Set<string>();
  const parseableContent = content.replace(
    FINAL_OUTPUT_SANDBOX_SCHEME_REGEX,
    "$1",
  );

  for (const match of parseableContent.matchAll(FINAL_OUTPUT_FILE_PATH_REGEX)) {
    const filePath = normalizeOutputPath(match[0]);
    if (!filePath || filePath.startsWith("//") || filePath.includes("://")) {
      continue;
    }

    const name = getOutputFileNameFromPath(filePath);
    const type = getFileTypeFromName(name);
    if (!name || !FINAL_OUTPUT_FILE_EXTENSIONS.has(type)) {
      continue;
    }

    const identity = normalizeOutputPath(filePath).toLowerCase();
    if (seen.has(identity)) continue;
    seen.add(identity);
    fileInfos.push({ name, path: filePath, kind: artifactKind(type) });
  }

  return fileInfos;
}

function getFileInfoIdentities(file: ExtractedOutputFile): string[] {
  return [file.path, file.name]
    .filter(Boolean)
    .map((value) => normalizeOutputPath(value).toLowerCase());
}

export function mergeFileInfoLists(
  existingFileList: ExtractedOutputFile[],
  extractedFileList: ExtractedOutputFile[],
): ExtractedOutputFile[] {
  const merged = [...existingFileList];
  const mergedIdentities = merged.map(getFileInfoIdentities);

  for (const file of extractedFileList) {
    const identities = getFileInfoIdentities(file);
    const existingIndex = mergedIdentities.findIndex((existingIdentities) =>
      identities.some((identity) => existingIdentities.includes(identity)),
    );
    if (existingIndex === -1) {
      merged.push(file);
      mergedIdentities.push(identities);
    }
  }
  return merged;
}
