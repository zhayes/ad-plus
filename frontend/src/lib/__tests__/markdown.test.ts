import { describe, expect, it } from "vitest";
import { renderMarkdown } from "../markdown";

describe("renderMarkdown", () => {
  it("escapes html before styling", () => {
    const html = renderMarkdown("<script>alert(1)</script> **粗**");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("<strong>粗</strong>");
  });

  it("renders fenced code without touching inner markers", () => {
    const html = renderMarkdown("```js\nconst a = 1 < 2;\n```");
    expect(html).toContain("<pre><code>");
    expect(html).toContain("1 &lt; 2");
  });

  it("builds tables and lists", () => {
    const html = renderMarkdown("| a | b |\n|---|---|\n| 1 | 2 |");
    expect(html).toContain("<table>");
    expect(html).toContain("<td>1</td>");

    const list = renderMarkdown("- one\n- two");
    expect(list).toContain("<ul>");
    expect(list.match(/<li>/g)?.length).toBe(2);
  });
});
