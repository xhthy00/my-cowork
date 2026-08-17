/**
 * Excel/CSV preview + lightweight cell-value editing via SheetJS.
 */
import { ExternalLink, Loader2, Save } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { fileBasename, normalizeFsPath } from "@/lib/fsPath";
import {
  columnLabel,
  gridsEqual,
  LARGE_FILE_PREVIEW_ROWS,
  MAX_EDITABLE_CELLS,
  parseWorkbookBuffer,
  serializeCsv,
  serializeXlsx,
  setCell,
  truncateForPreview,
  type SheetModel,
} from "@/lib/sheetjs";
import { usePreviewStore } from "@/store/preview";
import { cn } from "@/lib/utils";

type Ext = "xlsx" | "csv";

export default function SpreadsheetEditor({
  path,
  ext,
  tabId,
}: {
  path: string;
  ext: Ext;
  tabId?: string;
}) {
  const safePath = useMemo(() => normalizeFsPath(path) || path, [path]);
  const setPathDirty = usePreviewStore((s) => s.setPathDirty);
  const updateFileTab = usePreviewStore((s) => s.updateFileTab);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sheets, setSheets] = useState<SheetModel[]>([]);
  const [baseline, setBaseline] = useState<SheetModel[]>([]);
  const [active, setActive] = useState(0);
  const [readOnly, setReadOnly] = useState(false);
  const [cellCount, setCellCount] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [editCell, setEditCell] = useState<{ r: number; c: number } | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const dirty = useMemo(() => {
    if (readOnly || sheets.length !== baseline.length) return false;
    for (let i = 0; i < sheets.length; i++) {
      if (sheets[i].name !== baseline[i].name) return true;
      if (!gridsEqual(sheets[i].grid, baseline[i].grid)) return true;
    }
    return false;
  }, [sheets, baseline, readOnly]);

  useEffect(() => {
    setPathDirty(safePath, dirty);
    return () => setPathDirty(safePath, false);
  }, [safePath, dirty, setPathDirty]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setSaveMsg("");
    setEditCell(null);
    try {
      if (!window.api.readFileBuffer) {
        throw new Error("readFileBuffer 不可用（请重启 Electron）");
      }
      const res = await window.api.readFileBuffer(safePath);
      if (!res.ok || !res.data) throw new Error(res.error || "读取失败");
      const model = parseWorkbookBuffer(res.data, ext);
      const display = model.readOnly
        ? truncateForPreview(model.sheets)
        : model.sheets;
      setSheets(display);
      setBaseline(display.map((s) => ({ name: s.name, grid: s.grid.map((r) => r.slice()) })));
      setActive(0);
      setReadOnly(model.readOnly);
      setCellCount(model.cellCount);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSheets([]);
      setBaseline([]);
    } finally {
      setLoading(false);
    }
  }, [safePath, ext]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (editCell) inputRef.current?.focus();
  }, [editCell]);

  const current = sheets[active];

  const commitEdit = useCallback(() => {
    if (!editCell || readOnly || !current) return;
    const { r, c } = editCell;
    setSheets((prev) =>
      prev.map((s, i) =>
        i === active ? { ...s, grid: setCell(s.grid, r, c, draft) } : s,
      ),
    );
    setEditCell(null);
  }, [editCell, readOnly, current, active, draft]);

  const startEdit = (r: number, c: number) => {
    if (readOnly || !current) return;
    setEditCell({ r, c });
    setDraft(current.grid[r]?.[c] ?? "");
  };

  const writeBytes = async (
    targetPath: string,
    allowCreate: boolean,
  ): Promise<boolean> => {
    if (!window.api.writeFileBuffer) {
      setSaveMsg("writeFileBuffer 不可用");
      return false;
    }
    const data =
      ext === "csv"
        ? serializeCsv(sheets[0] || { name: "Sheet1", grid: [[""]] })
        : serializeXlsx(sheets);
    const res = await window.api.writeFileBuffer(targetPath, data, {
      allowCreate,
    });
    if (!res.ok) {
      setSaveMsg(res.error || "保存失败");
      return false;
    }
    return true;
  };

  const onSave = async () => {
    if (readOnly || !dirty) return;
    setSaving(true);
    setSaveMsg("");
    try {
      const ok = await writeBytes(safePath, false);
      if (ok) {
        setBaseline(sheets.map((s) => ({ name: s.name, grid: s.grid.map((r) => r.slice()) })));
        setSaveMsg("已保存");
      }
    } finally {
      setSaving(false);
    }
  };

  const onSaveAs = async () => {
    if (readOnly) return;
    if (!window.api.saveFileDialog) {
      setSaveMsg("saveFileDialog 不可用");
      return;
    }
    setSaving(true);
    setSaveMsg("");
    try {
      const base = fileBasename(safePath) || (ext === "csv" ? "export.csv" : "export.xlsx");
      const dlg = await window.api.saveFileDialog({
        defaultPath: base,
        filters:
          ext === "csv"
            ? [{ name: "CSV", extensions: ["csv"] }]
            : [{ name: "Excel", extensions: ["xlsx"] }],
      });
      if (dlg.canceled || !dlg.filePath) return;
      const ok = await writeBytes(dlg.filePath, true);
      if (ok) {
        setBaseline(sheets.map((s) => ({ name: s.name, grid: s.grid.map((r) => r.slice()) })));
        setPathDirty(safePath, false);
        if (tabId) {
          updateFileTab(tabId, {
            path: dlg.filePath,
            title: fileBasename(dlg.filePath),
          });
        }
        setSaveMsg("已另存为");
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-ds-text-neutral-muted-default">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-body-sm">加载表格…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-4 text-center">
        <p className="text-body-sm text-ds-text-error-default-default">{error}</p>
        <Button size="sm" variant="outline" onClick={() => void window.api.ipcOpenPath(safePath)}>
          在系统中打开
        </Button>
      </div>
    );
  }

  const cols = current?.grid[0]?.length ?? 0;
  const rows = current?.grid.length ?? 0;
  const activeCellLabel =
    editCell != null ? `${columnLabel(editCell.c)}${editCell.r + 1}` : "—";

  return (
    <div className="sheet-editor flex h-full min-h-0 flex-1 flex-col">
      <div className="sheet-editor-toolbar shrink-0">
        <div className="sheet-editor-toolbar-left">
          <span className="sheet-editor-badge">{ext === "csv" ? "CSV" : "Excel"}</span>
          {dirty ? <span className="sheet-editor-dirty">未保存</span> : null}
          {saveMsg ? <span className="sheet-editor-status">{saveMsg}</span> : null}
          {!readOnly && editCell ? (
            <span className="sheet-editor-cell-ref" title="当前编辑单元格">
              {activeCellLabel}
            </span>
          ) : null}
        </div>
        <div className="sheet-editor-toolbar-right">
          {!readOnly ? (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 px-2.5 text-xs"
                disabled={!dirty || saving}
                onClick={() => void onSave()}
                title="保存到原文件"
              >
                <Save className="h-3.5 w-3.5" />
                保存
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2.5 text-xs"
                disabled={saving}
                onClick={() => void onSaveAs()}
              >
                另存为
              </Button>
            </>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1 px-2.5 text-xs"
            onClick={() => void window.api.ipcOpenPath(safePath)}
          >
            <ExternalLink className="h-3.5 w-3.5" />
            系统打开
          </Button>
        </div>
      </div>

      {readOnly ? (
        <p className="sheet-editor-hint sheet-editor-hint-warn shrink-0">
          表格过大（约 {cellCount.toLocaleString()} 格，阈值{" "}
          {MAX_EDITABLE_CELLS.toLocaleString()}），仅预览前 {LARGE_FILE_PREVIEW_ROWS}{" "}
          行；请用系统 Excel 编辑。
        </p>
      ) : (
        <p className="sheet-editor-hint shrink-0">
          双击单元格编辑 · 编辑公式格后写回为常量 · Enter 下移 / Tab 右移
        </p>
      )}

      <div className="sheet-editor-grid min-h-0 flex-1 overflow-auto">
        {!current ? null : (
          <table className="sheet-table">
            <thead>
              <tr>
                <th className="sheet-corner" />
                {Array.from({ length: cols }, (_, c) => (
                  <th
                    key={c}
                    className={cn(
                      "sheet-col-header",
                      editCell?.c === c && "is-active-col",
                    )}
                  >
                    {columnLabel(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rows }, (_, r) => (
                <tr key={r} className={cn(r % 2 === 1 && "sheet-row-alt")}>
                  <th
                    className={cn(
                      "sheet-row-header",
                      editCell?.r === r && "is-active-row",
                    )}
                  >
                    {r + 1}
                  </th>
                  {Array.from({ length: cols }, (_, c) => {
                    const editing =
                      !readOnly && editCell?.r === r && editCell?.c === c;
                    const val = current.grid[r]?.[c] ?? "";
                    const looksNumber =
                      val !== "" && /^-?\d+(\.\d+)?%?$/.test(val.trim());
                    return (
                      <td
                        key={c}
                        className={cn(
                          "sheet-cell",
                          editing && "is-editing",
                        )}
                        onDoubleClick={() => startEdit(r, c)}
                      >
                        {editing ? (
                          <input
                            ref={inputRef}
                            className="sheet-cell-input"
                            value={draft}
                            onChange={(e) => setDraft(e.target.value)}
                            onBlur={() => commitEdit()}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                commitEdit();
                                if (r + 1 < rows) startEdit(r + 1, c);
                              } else if (e.key === "Tab") {
                                e.preventDefault();
                                commitEdit();
                                if (c + 1 < cols) startEdit(r, c + 1);
                                else if (r + 1 < rows) startEdit(r + 1, 0);
                              } else if (e.key === "Escape") {
                                setEditCell(null);
                              }
                            }}
                          />
                        ) : (
                          <div
                            className={cn(
                              "sheet-cell-value",
                              looksNumber && "is-number",
                            )}
                          >
                            {val}
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="sheet-editor-tabs shrink-0">
        <div className="sheet-editor-tabs-scroll">
          {sheets.map((s, i) => (
            <button
              key={`${s.name}-${i}`}
              type="button"
              className={cn("sheet-tab", i === active && "is-active")}
              onClick={() => {
                commitEdit();
                setActive(i);
              }}
            >
              {s.name}
            </button>
          ))}
        </div>
        <span className="sheet-editor-meta">
          {rows.toLocaleString()} × {cols.toLocaleString()}
        </span>
      </div>
    </div>
  );
}
