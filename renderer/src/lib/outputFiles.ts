/**
 * Side-panel "输出文件夹" / chat artifact chips: final deliverables only.
 */

const DELIVERABLE_EXT =
  /\.(png|jpe?g|webp|gif|svg|bmp|pdf|docx?|pptx?|xlsx|csv|html?|md)$/i;

/** Plain .txt / .json are almost always agent scratch fragments. */
const SCRATCH_EXT = /\.(txt|json|py|sh|bash|js|mjs|cjs|ts|tsx|log|tmp)$/i;

const PROCESS_NAME =
  /^(requirements\.txt|pyproject\.toml|package\.json|uv\.lock|\.gitignore|skill\.md)$/i;

/** Intermediate build pieces (html_part1, skeleton, script2, …). */
const INTERMEDIATE_NAME =
  /(^|[_-])(part\d*|skeleton|wrapper|head|style|script\d*|script_b64|test|tmp|temp|draft|chart_data|with_data|html_head|html_script|html_part)([._-]|$)/i;

/**
 * Throwaway probe/test file names agents create while experimenting
 * (t_nf_0.0.xlsx, tC.xlsx, x1_check.xlsx, tmp_build.xlsx, …).
 * Multi-letter keywords need a separator/end after them (checklist.xlsx stays);
 * single letters (t/x/z) REQUIRE a separator so table_销售.xlsx survives.
 */
const PROBE_NAME =
  /^(?:(?:tmp|temp|test|try|probe|chk|check|demo|sample)\d*(?=[_-]|$)|(?:[txz]\d*)[_-])/i;

/** Excel number-format tokens (#,##0 / 0.0% / $#,##0) baked into probe names. */
const FORMAT_TOKEN = /[#%]|\$#/;

function looksLikeProbeBasename(stem: string): boolean {
  // Ultra-short throwaway stems: tC, x2, z9 …
  if (stem.length <= 3 && /^[txzTXZ][A-Z0-9]/.test(stem)) return true;
  const match = stem.match(PROBE_NAME);
  if (!match) return false;
  // Only treat as probe when the remainder is short (a tag, not a real title).
  return stem.slice(match[0].length).length <= 8;
}

export function isDeliverableOutputPath(filePath: string): boolean {
  const normalized = filePath.replace(/\\/g, "/");
  if (normalized.includes("/_scratch/") || normalized.includes("/.venv/")) {
    return false;
  }
  const name = normalized.split("/").pop() || "";
  if (!name || name.startsWith(".")) return false;
  if (PROCESS_NAME.test(name)) return false;
  if (SCRATCH_EXT.test(name)) return false;
  if (INTERMEDIATE_NAME.test(name)) return false;
  if (FORMAT_TOKEN.test(name)) return false;
  const dot = name.lastIndexOf(".");
  const stem = dot > 0 ? name.slice(0, dot) : name;
  if (looksLikeProbeBasename(stem)) return false;
  return DELIVERABLE_EXT.test(name);
}
