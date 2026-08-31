import { describe, expect, it } from "vitest";

import { artifactIdentity } from "../../renderer/src/lib/fsPath";

describe("artifactIdentity", () => {
  it("collapses Windows slash and drive-letter variants", () => {
    const a = artifactIdentity(
      "C:\\Users\\xhthy\\.my-cowork\\spaces\\s1\\评估报告.html",
    );
    const b = artifactIdentity(
      "C:/Users/xhthy/.my-cowork/spaces/s1/评估报告.html",
    );
    const c = artifactIdentity(
      "c:\\Users\\xhthy\\.my-cowork\\spaces\\s1\\评估报告.html",
    );
    expect(a).toBe(b);
    expect(a).toBe(c);
    expect(a).toContain("评估报告.html");
  });

  it("keeps distinct files distinct", () => {
    expect(artifactIdentity("/tmp/a.html")).not.toBe(
      artifactIdentity("/tmp/b.html"),
    );
  });
});
