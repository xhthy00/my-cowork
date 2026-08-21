/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UserMessageRichContent } from "../../renderer/src/components/chat/UserMessageRichContent";

describe("UserMessageRichContent", () => {
  it("highlights @connector and URL after send", () => {
    render(
      <UserMessageRichContent content="@fetch 帮我获取该网页内容形成md文档，https://www.jianshu.com/p/ccb88e69c3c6" />,
    );
    const chip = screen.getByText("@fetch");
    expect(chip.getAttribute("data-rich-connector")).toBe("1");
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toContain("jianshu.com");
  });

  it("highlights #skill chips", () => {
    render(<UserMessageRichContent content="用 #weekly-report 写周报" />);
    const chip = screen.getByText("#weekly-report");
    expect(chip.getAttribute("data-rich-skill")).toBe("1");
  });
});
