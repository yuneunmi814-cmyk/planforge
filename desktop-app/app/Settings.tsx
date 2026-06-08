"use client";

import { useEffect, useState } from "react";
import { getSettings, listOllamaModels, Settings, updateSettings } from "./lib/backend";
import { useI18n } from "./lib/i18n";

export default function SettingsPanel({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [s, setS] = useState<Settings | null>(null);
  const [key, setKey] = useState("");
  const [ollama, setOllama] = useState<{ available: boolean; models: string[] }>({ available: false, models: [] });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getSettings().then(setS).catch((e) => setError(String(e)));
    listOllamaModels().then(setOllama).catch(() => {});
  }, []);

  if (!s) return <Card>{t("settings.loading")}</Card>;

  async function save(patch: Partial<Settings> & { anthropicApiKey?: string }) {
    setError("");
    try {
      const next = await updateSettings(patch);
      setS(next);
      setKey("");
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>{t("settings.title")}</h2>
        <button onClick={onClose} style={ghostBtn}>{t("settings.close")}</button>
      </div>

      <p style={{ color: "#666", fontSize: 13 }}>{t("settings.intro")}</p>

      <label style={lbl}>{t("settings.engine")}</label>
      <div style={{ display: "flex", gap: 8 }}>
        <Choice active={s.llmProvider === "ollama"} onClick={() => save({ llmProvider: "ollama" })}>
          {t("settings.engine.ollama")}
        </Choice>
        <Choice active={s.llmProvider === "anthropic"} onClick={() => save({ llmProvider: "anthropic" })}>
          {t("settings.engine.anthropic")}
        </Choice>
      </div>

      {s.llmProvider === "ollama" && (
        <>
          <label style={lbl}>
            {t("settings.model")}{" "}
            ({ollama.available ? t("settings.model.installed", { n: ollama.models.length }) : t("settings.ollama.down")})
          </label>
          <input
            list="ollama-models"
            defaultValue={s.ollamaModel}
            onBlur={(e) => e.target.value && save({ ollamaModel: e.target.value })}
            style={input}
          />
          <datalist id="ollama-models">
            {ollama.models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          {!ollama.available && (
            <p style={{ color: "#b3261e", fontSize: 12 }}>{t("settings.ollama.hint", { model: s.ollamaModel })}</p>
          )}
        </>
      )}

      {s.llmProvider === "anthropic" && (
        <>
          <label style={lbl}>
            {t("settings.key")}{" "}
            ({s.hasAnthropicKey ? t("settings.key.saved", { masked: s.anthropicKeyMasked }) : t("settings.key.unset")})
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="password"
              placeholder="sk-ant-…"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              style={{ ...input, flex: 1 }}
            />
            <button onClick={() => save({ anthropicApiKey: key })} disabled={!key} style={primaryBtn}>
              {t("settings.key.save")}
            </button>
          </div>
          <p style={{ color: "#888", fontSize: 12 }}>{t("settings.key.note")}</p>
        </>
      )}

      {saved && <p style={{ color: "#1a7a3a", fontSize: 13 }}>{t("settings.saved")}</p>}
      {error && <p style={{ color: "#b3261e", fontSize: 13 }}>{error}</p>}
    </Card>
  );
}

const lbl: React.CSSProperties = { display: "block", marginTop: 16, marginBottom: 6, fontSize: 13, fontWeight: 600 };
const input: React.CSSProperties = { padding: 10, fontSize: 14, borderRadius: 8, border: "1px solid #ddd", width: "100%", boxSizing: "border-box" };
const primaryBtn: React.CSSProperties = { padding: "10px 16px", borderRadius: 8, border: "none", background: "#1a1a1a", color: "#fff", cursor: "pointer" };
const ghostBtn: React.CSSProperties = { padding: "6px 12px", borderRadius: 8, border: "1px solid #ddd", background: "#fff", cursor: "pointer" };

function Choice({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: "10px 12px",
        borderRadius: 8,
        border: active ? "2px solid #1a1a1a" : "1px solid #ddd",
        background: active ? "#f4f4f4" : "#fff",
        fontWeight: active ? 600 : 400,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 20, background: "#fff", marginTop: 16 }}>
      {children}
    </div>
  );
}
