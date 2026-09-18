import katex from "katex";

/** Minimal markdown → HTML for lesson/chat content, with LaTeX support.
 * Math is rendered first and stashed behind placeholder tokens so HTML
 * escaping never mangles KaTeX output. Supports \( \), \[ \], $$ $$. */
const HOLE = "%%MATHHOLE";

export function mdToHtml(md: string): string {
  const holes: string[] = [];
  const stash = (html: string) => {
    holes.push(html);
    return `${HOLE}${holes.length - 1}%%`;
  };
  const math = (tex: string, display: boolean) => {
    try {
      return stash(katex.renderToString(tex, { displayMode: display, throwOnError: false }));
    } catch {
      return tex;
    }
  };

  let s = md
    .replace(/\\\[([\s\S]+?)\\\]/g, (_m, t) => math(t, true))
    .replace(/\$\$([\s\S]+?)\$\$/g, (_m, t) => math(t, true))
    .replace(/\\\((.+?)\\\)/g, (_m, t) => math(t, false));

  s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // fenced code
  s = s.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang, code) => `<pre><code>${code}</code></pre>`);
  // headings
  s = s.replace(/^### (.*)$/gm, "<h4>$1</h4>");
  s = s.replace(/^## (.*)$/gm, "<h3>$1</h3>");
  s = s.replace(/^# (.*)$/gm, "<h3>$1</h3>");
  // bold / italic / inline code
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|\W)\*([^*\n]+)\*(?=\W|$)/g, "$1<em>$2</em>");
  s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  // unordered lists
  s = s.replace(/((?:^[-*] .*(?:\n|$))+)/gm, (m) => {
    const items = m
      .trim()
      .split("\n")
      .map((l) => `<li>${l.replace(/^[-*] /, "")}</li>`)
      .join("");
    return `<ul>${items}</ul>`;
  });
  // ordered lists
  s = s.replace(/((?:^\d+\. .*(?:\n|$))+)/gm, (m) => {
    const items = m
      .trim()
      .split("\n")
      .map((l) => `<li>${l.replace(/^\d+\. /, "")}</li>`)
      .join("");
    return `<ol>${items}</ol>`;
  });
  // paragraphs
  s = s
    .split(/\n{2,}/)
    .map((p) => (p.match(/^<(h3|h4|ul|ol|pre)/) ? p : `<p>${p.replace(/\n/g, "<br/>")}</p>`))
    .join("");

  // restore rendered math
  return s.replace(/%%MATHHOLE(\d+)%%/g, (_m, i) => holes[Number(i)]);
}
