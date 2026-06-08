"use client";

import { useEffect, useState } from "react";
import SettingsPanel from "./Settings";
import { createProject, getProjectDetail, Section, waitForBackend, waitForJob } from "./lib/backend";
import { useI18n } from "./lib/i18n";

const TOTAL_SECTIONS = 9;

type Phase = "booting" | "ready" | "generating" | "done" | "error";

export default function Home() {
  const { t, locale, setLocale } = useI18n();
  const [phase, setPhase] = useState<Phase>("booting");
  const [idea, setIdea] = useState("");
  const [status, setStatus] = useState("");
  const [sections, setSections] = useState<Section[]>([]);
  const [missing, setMissing] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [showSettings, setShowSettings] = useState(false);

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
    setPhase("generating");
    try {
      const { projectId, jobId } = await createProject(idea.trim());
      const final = await waitForJob(projectId, jobId, setStatus);
      if (final !== "success") {
        setError(t("generate.result", { status: final }));
        setPhase("error");
        return;
      }
      const detail = await getProjectDetail(projectId);
      setSections(detail.sections);
      setMissing(detail.missingSections);
      setPhase("done");
    } catch (e) {
      setError(String(e));
      setPhase("error");
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
        </>
      )}

      {missing.length > 0 && (
        <Banner tone="warn">
          {t("generate.partial", { got: TOTAL_SECTIONS - missing.length, total: TOTAL_SECTIONS })}
        </Banner>
      )}

      {sections.map((s) => (
        <section key={s.type} style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 18, borderBottom: "1px solid #eee", paddingBottom: 6 }}>{s.title}</h2>
          <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 14, lineHeight: 1.6 }}>
            {s.markdown}
          </pre>
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

function Banner({ children, tone }: { children: React.ReactNode; tone?: "error" | "warn" }) {
  const bg = tone === "error" ? "#fdecea" : tone === "warn" ? "#fff6e6" : "#eef4ff";
  const fg = tone === "error" ? "#b3261e" : tone === "warn" ? "#8a5a00" : "#1a3a7a";
  return (
    <div style={{ margin: "16px 0", padding: "12px 16px", borderRadius: 8, background: bg, color: fg, fontSize: 14 }}>
      {children}
    </div>
  );
}
