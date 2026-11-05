/** Small, dependency-free markdown renderer — ported from the legacy page.

 * Supports fenced code, tables, headings, hr, blockquote, lists, emphasis,
 * inline code and links. Escapes everything first, so it is safe to inject.
 */

const escapeHtml = (text: string): string =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function inline(text: string): string {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}

export function renderMarkdown(text: string): string {
  const lines = String(text ?? "").replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let list: "ul" | "ol" | null = null;
  let para: string[] = [];
  let i = 0;

  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${inline(para.join(" "))}</p>`);
      para = [];
    }
  };
  const closeList = () => {
    if (list) {
      out.push(`</${list}>`);
      list = null;
    }
  };

  while (i < lines.length) {
    const line = lines[i]!;

    if (/^\s*```/.test(line)) {
      flushPara();
      closeList();
      const buf: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i]!)) {
        buf.push(lines[i]!);
        i += 1;
      }
      i += 1;
      out.push(`<pre><code>${escapeHtml(buf.join("\n"))}</code></pre>`);
      continue;
    }

    const next = lines[i + 1] ?? "";
    if (line.includes("|") && /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(next)) {
      flushPara();
      closeList();
      const split = (row: string) =>
        row.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
      const head = split(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i]!.includes("|") && lines[i]!.trim()) {
        rows.push(split(lines[i]!));
        i += 1;
      }
      const th = head.map((c) => `<th>${inline(c)}</th>`).join("");
      const body = rows
        .map((r) => `<tr>${head.map((_, idx) => `<td>${inline(r[idx] ?? "")}</td>`).join("")}</tr>`)
        .join("");
      out.push(`<table><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table>`);
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushPara();
      closeList();
      const level = Math.min(3, heading[1]!.length);
      out.push(`<h${level}>${inline(heading[2]!)}</h${level}>`);
      i += 1;
      continue;
    }

    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
      flushPara();
      closeList();
      out.push("<hr>");
      i += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      flushPara();
      closeList();
      const buf: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i]!)) {
        buf.push(lines[i]!.replace(/^\s*>\s?/, ""));
        i += 1;
      }
      out.push(`<blockquote>${inline(buf.join(" "))}</blockquote>`);
      continue;
    }

    const ul = line.match(/^\s*[-*+]\s+(.*)$/);
    const ol = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ul || ol) {
      flushPara();
      const want = ul ? "ul" : "ol";
      if (list !== want) {
        closeList();
        out.push(`<${want}>`);
        list = want;
      }
      out.push(`<li>${inline((ul ?? ol)![1]!)}</li>`);
      i += 1;
      continue;
    }

    if (!line.trim()) {
      flushPara();
      closeList();
      i += 1;
      continue;
    }

    para.push(line.trim());
    i += 1;
  }

  flushPara();
  closeList();
  return out.join("\n");
}
