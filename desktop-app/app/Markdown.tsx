"use client";

// Renders a generated section as real markdown: GFM tables, headings, code — and
// turns ```mermaid fenced blocks (the architecture diagram) into actual diagrams.
// Mermaid is imported lazily inside an effect so it never runs during the static
// export build (it touches the DOM at load).

import { useEffect, useId, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Part = { type: "md" | "mermaid"; text: string };

/** Split out ```mermaid blocks so they render as diagrams, the rest as markdown. */
function splitMermaid(md: string): Part[] {
  const re = /```mermaid\s*\n([\s\S]*?)```/g;
  const parts: Part[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(md)) !== null) {
    if (m.index > last) parts.push({ type: "md", text: md.slice(last, m.index) });
    parts.push({ type: "mermaid", text: m[1].trim() });
    last = m.index + m[0].length;
  }
  if (last < md.length) parts.push({ type: "md", text: md.slice(last) });
  return parts.length ? parts : [{ type: "md", text: md }];
}

function Mermaid({ chart }: { chart: string }) {
  const id = "mmd-" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
        const { svg } = await mermaid.render(id, chart);
        if (!cancelled) setSvg(svg);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart, id]);

  // On failure, fall back to the raw mermaid source so nothing is lost.
  if (failed) return <pre style={codeBlock}>{chart}</pre>;
  if (!svg) return <p style={{ color: "#888", fontSize: 13 }}>다이어그램 렌더링 중…</p>;
  return (
    <div
      style={{ overflowX: "auto", margin: "12px 0", textAlign: "center" }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

const mdComponents = {
  table: (p: React.ComponentProps<"table">) => (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 14, margin: "8px 0" }} {...p} />
    </div>
  ),
  th: (p: React.ComponentProps<"th">) => (
    <th style={{ border: "1px solid #e2e5ea", padding: "6px 10px", background: "#f6f8fa", textAlign: "left" }} {...p} />
  ),
  td: (p: React.ComponentProps<"td">) => (
    <td style={{ border: "1px solid #e2e5ea", padding: "6px 10px", verticalAlign: "top" }} {...p} />
  ),
  code: (p: React.ComponentProps<"code">) => {
    const cls = p.className || "";
    // Fenced (non-mermaid) blocks have a language-* class; inline code has none.
    return /language-/.test(cls) ? (
      <code style={codeBlock as React.CSSProperties} className={cls}>
        {p.children}
      </code>
    ) : (
      <code style={inlineCode}>{p.children}</code>
    );
  },
};

const codeBlock: React.CSSProperties = {
  display: "block",
  whiteSpace: "pre-wrap",
  background: "#f6f8fa",
  border: "1px solid #e2e5ea",
  borderRadius: 6,
  padding: "10px 12px",
  fontSize: 13,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  overflowX: "auto",
};
const inlineCode: React.CSSProperties = {
  background: "#f0f1f3",
  borderRadius: 4,
  padding: "1px 5px",
  fontSize: 13,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

export default function Markdown({ children }: { children: string }) {
  const parts = splitMermaid(children);
  return (
    <div style={{ fontSize: 14, lineHeight: 1.7 }}>
      {parts.map((p, i) =>
        p.type === "mermaid" ? (
          <Mermaid key={i} chart={p.text} />
        ) : (
          <ReactMarkdown key={i} remarkPlugins={[remarkGfm]} components={mdComponents}>
            {p.text}
          </ReactMarkdown>
        ),
      )}
    </div>
  );
}
