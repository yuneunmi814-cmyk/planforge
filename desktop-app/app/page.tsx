"use client";

import { useEffect, useState } from "react";
import Markdown from "./Markdown";
import SettingsPanel from "./Settings";
import {
  createProject,
  exportText,
  type ExportFormat,
  getManualPrompt,
  getProjectDetail,
  importManual,
  openChat,
  revealExport,
  saveExport,
  Section,
  waitForBackend,
  waitForJob,
} from "./lib/backend";
import { useI18n } from "./lib/i18n";

type Phase = "booting" | "ready" | "generating" | "done" | "error";

export default function Home() {
  const { t, locale, setLocale } = useI18n();
  const [phase, setPhase] = useState<Phase>("booting");
  const [idea, setIdea] = useState("");
  const [status, setStatus] = useState("");
  const [sections, setSections] = useState<Section[]>([]);
  const [missing, setMissing] = useState<string[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [exportMsg, setExportMsg] = useState("");
  const [lastSaved, setLastSaved] = useState<{ format: ExportFormat; path: string } | null>(null);
  const [error, setError] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [pasted, setPasted] = useState("");
  const [manualMsg, setManualMsg] = useState("");

  useEffect(() => {
    waitForBackend()
      .then(() => setPhase("ready"))
      .catch((e) => {
        setError(String(e));
        setPhase("error");
      });
  }, []);

  async function onGenerate() {
    setError("");
    setSections([]);
    setMissing([]);
    setProjectId(null);
    setExportMsg("");
    setLastSaved(null);
    setPhase("generating");
    try {
      const { projectId: pid, jobId } = await createProject(idea.trim());
      const final = await waitForJob(pid, jobId, setStatus);
      if (final !== "success") {
        setError(t("generate.result", { status: final }));
        setPhase("error");
        return;
      }
      const detail = await getProjectDetail(pid);
      setSections(detail.sections);
      setMissing(detail.missingSections);
      setProjectId(pid);
      setPhase("done");
    } catch (e) {
      setError(String(e));
      setPhase("error");
    }
  }

  async function onCopy() {
    if (projectId == null) return;
    try {
      await navigator.clipboard.writeText(await exportText(projectId, "md"));
      setLastSaved(null);
      setExportMsg(t("export.copied"));
    } catch {
      setExportMsg(t("export.copyFailed"));
    }
  }

  async function onSave(format: ExportFormat) {
    if (projectId == null) return;
    try {
      const saved = await saveExport(projectId, format);
      setLastSaved({ format, path: saved.path });
      setExportMsg(t("export.saved", { path: saved.path }));
    } catch (e) {
      setExportMsg(t("export.failed", { msg: String(e) }));
    }
  }

  async function onReveal() {
    if (projectId == null || !lastSaved) return;
    await revealExport(projectId, lastSaved.format);
  }

  async function onCopyPrompt() {
    if (!idea.trim()) return;
    try {
      const prompt = await getManualPrompt(idea.trim());
      await navigator.clipboard.writeText(prompt);
      setManualMsg(t("manual.copied"));
    } catch (e) {
      setManualMsg(t("manual.failed", { msg: String(e) }));
    }
  }

  async function onImport() {
    if (!idea.trim() || !pasted.trim()) return;
    setManualMsg(t("manual.importing"));
    try {
      const r = await importManual(idea.trim(), pasted);
      if (r.status === "rejected") {
        setManualMsg(t("manual.rejected", { reason: r.reason ?? "" }));
        return;
      }
      if (r.projectId == null) {
        setManualMsg(t("manual.failed", { msg: "no project" }));
        return;
      }
      const detail = await getProjectDetail(r.projectId);
      setSections(detail.sections);
      setMissing(detail.missingSections);
      setProjectId(r.projectId);
      setExportMsg("");
      setLastSaved(null);
      setManualMsg("");
      setManualOpen(false);
      setPasted("");
      setPhase("done");
    } catch (e) {
      setManualMsg(t("manual.failed", { msg: String(e) }));
    }
  }

  return (
    <main style={{ maxWidth: 860, margin: "0 auto", padding: "32px 24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 style={{ fontSize: 28, marginBottom: 4 }}>PlanForge</h1>
          <p style={{ color: "#666", marginTop: 0 }}>{t("app.tagline")}</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setLocale(locale === "en" ? "ko" : "en")} style={btn}>
            {locale === "en" ? "한국어" : "English"}
          </button>
          {phase !== "booting" && (
            <button onClick={() => setShowSettings((v) => !v)} style={btn}>
              ⚙ {t("nav.settings")}
            </button>
          )}
        </div>
      </div>

      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}

      {phase === "booting" && <Banner>{t("app.booting")}</Banner>}
      {phase === "error" && <Banner tone="error">{error || t("app.error")}</Banner>}

      {phase !== "booting" && (
        <>
          <textarea
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            placeholder={t("idea.placeholder")}
            rows={3}
            disabled={phase === "generating"}
            style={{ width: "100%", padding: 12, fontSize: 15, borderRadius: 8, border: "1px solid #ddd", boxSizing: "border-box" }}
          />
          <button
            onClick={onGenerate}
            disabled={!idea.trim() || phase === "generating"}
            style={{
              marginTop: 12,
              padding: "10px 20px",
              fontSize: 15,
              borderRadius: 8,
              border: "none",
              background: phase === "generating" ? "#aaa" : "#1a1a1a",
              color: "#fff",
              cursor: phase === "generating" ? "default" : "pointer",
            }}
          >
            {phase === "generating" ? t("generate.running", { status }) : t("generate.button")}
          </button>

          <div style={{ marginTop: 10 }}>
            <button onClick={() => setManualOpen((v) => !v)} style={linkBtn}>
              {manualOpen ? t("manual.hide") : t("manual.toggle")}
            </button>
          </div>

          {manualOpen && (
            <div style={{ marginTop: 10, padding: 16, borderRadius: 10, background: "#f7f8fa", border: "1px solid #e5e7eb" }}>
              <p style={{ marginTop: 0, fontSize: 13, color: "#555" }}>{t("manual.intro")}</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                <button onClick={onCopyPrompt} disabled={!idea.trim()} style={btn}>{t("manual.copyPrompt")}</button>
                <span style={{ fontSize: 13, color: "#888" }}>{t("manual.openIn")}</span>
                <button onClick={() => openChat("chatgpt")} style={btn}>ChatGPT</button>
                <button onClick={() => openChat("claude")} style={btn}>Claude</button>
                <button onClick={() => openChat("gemini")} style={btn}>Gemini</button>
              </div>
              <textarea
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
                placeholder={t("manual.pastePlaceholder")}
                rows={5}
                style={{ marginTop: 12, width: "100%", padding: 12, fontSize: 14, borderRadius: 8, border: "1px solid #ddd", boxSizing: "border-box", fontFamily: "ui-monospace, monospace" }}
              />
              <button
                onClick={onImport}
                disabled={!idea.trim() || !pasted.trim()}
                style={{ marginTop: 8, padding: "10px 20px", fontSize: 15, borderRadius: 8, border: "none", background: !idea.trim() || !pasted.trim() ? "#aaa" : "#1a1a1a", color: "#fff", cursor: "pointer" }}
              >
                {t("manual.import")}
              </button>
              {manualMsg && <p style={{ fontSize: 13, color: "#555", marginBottom: 0 }}>{manualMsg}</p>}
            </div>
          )}
        </>
      )}

      {missing.length > 0 && (
        <Banner tone="warn">
          {t("generate.partial", { got: sections.length, total: sections.length + missing.length })}
        </Banner>
      )}

      {phase === "done" && sections.length > 0 && (
        <div style={{ marginTop: 20, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <button onClick={onCopy} style={btn}>{t("export.copy")}</button>
          <button onClick={() => onSave("md")} style={btn}>{t("export.saveMd")}</button>
          <button onClick={() => onSave("json")} style={btn}>{t("export.saveJson")}</button>
          {exportMsg && (
            <span style={{ fontSize: 13, color: "#555", display: "inline-flex", alignItems: "center", gap: 8 }}>
              {exportMsg}
              {lastSaved && (
                <button onClick={onReveal} style={linkBtn}>{t("export.reveal")}</button>
              )}
            </span>
          )}
        </div>
      )}

      {sections.map((s) => (
        <section key={s.type} style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 18, borderBottom: "1px solid #eee", paddingBottom: 6 }}>{s.title}</h2>
          <Markdown>{s.markdown}</Markdown>
        </section>
      ))}
    </main>
  );
}

const btn: React.CSSProperties = {
  padding: "8px 14px",
  borderRadius: 8,
  border: "1px solid #ddd",
  background: "#fff",
  cursor: "pointer",
};

const linkBtn: React.CSSProperties = {
  border: "none",
  background: "none",
  padding: 0,
  color: "#1a3a7a",
  textDecoration: "underline",
  cursor: "pointer",
  fontSize: 13,
};

function Banner({ children, tone }: { children: React.ReactNode; tone?: "error" | "warn" }) {
  const bg = tone === "error" ? "#fdecea" : tone === "warn" ? "#fff6e6" : "#eef4ff";
  const fg = tone === "error" ? "#b3261e" : tone === "warn" ? "#8a5a00" : "#1a3a7a";
  return (
    <div style={{ margin: "16px 0", padding: "12px 16px", borderRadius: 8, background: bg, color: fg, fontSize: 14 }}>
      {children}
    </div>
  );
}
