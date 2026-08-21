/**
 * Eigent-style visible agent file filter (runtime-only dirs + task roots).
 */
import { describe, expect, it } from "vitest";

import {
  isAgentTaskRootEntry,
  isVisibleAgentPath,
} from "../../renderer/src/lib/outputFiles";

describe("isVisibleAgentPath", () => {
  it("shows write-tool deliverables including md/json/png", () => {
    expect(isVisibleAgentPath("/tmp/proj/report.docx")).toBe(true);
    expect(isVisibleAgentPath("/tmp/proj/summary.md")).toBe(true);
    expect(isVisibleAgentPath("/tmp/proj/data.json")).toBe(true);
    expect(isVisibleAgentPath("/tmp/proj/现货黄金近期波动折线图.png")).toBe(true);
    expect(isVisibleAgentPath("/tmp/proj/script.py")).toBe(true);
  });

  it("hides camel_logs and .venv", () => {
    expect(
      isVisibleAgentPath(
        "/Users/test/.eigent/user/project_p/task_1/camel_logs/events.jsonl",
      ),
    ).toBe(false);
    expect(isVisibleAgentPath("/tmp/proj/.venv/lib/file.py")).toBe(false);
  });

  it("hides task root directory names", () => {
    expect(
      isAgentTaskRootEntry({
        name: "task_1784197841790-917",
        path: "/Users/test/.eigent/user/project_p/task_1784197841790-917",
        relativePath: "task_1784197841790-917",
      }),
    ).toBe(true);
    expect(
      isVisibleAgentPath("/Users/test/.eigent/user/project_p/task_1/index.html"),
    ).toBe(true);
  });
});
