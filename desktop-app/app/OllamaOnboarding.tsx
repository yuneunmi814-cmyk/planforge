"use client";

import { useCallback, useEffect, useState } from "react";
import { OllamaStatus, ollamaStatus, openOllamaDownload, pullOllamaModel } from "./lib/backend";
import { useI18n } from "./lib/i18n";

function hasModel(models: string[], model: string): boolean {
  return models.some((m) => m === model || m.split(":")[0] === model);
}

export default function OllamaOnboarding({ model }: { model: string }) {
  const { t } = useI18n();
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [pulling, setPulling] = useState(false);
  const [pct, setPct] = useState(0);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      setStatus(await ollamaStatus());
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onPull() {
    setPulling(true);
    setPct(0);
    setError("");
    try {
      await pullOllamaModel(model, (p) => {
        if (p.total) setPct(Math.round(((p.completed ?? 0) / p.total) * 100));
      });
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setPulling(false);
    }
  }

  if (!status) return <Box>{t("ob.checking")}</Box>;

  if (!status.installed) {
    return (
      <Box tone="warn">
        <b>{t("ob.notInstalled.title")}</b>
        <p style={p}>{t("ob.notInstalled.body")}</p>
        <Row>
          <button style={primary} onClick={() => openOllamaDownload()}>{t("ob.install")}</button>
          <button style={ghost} onClick={refresh}>{t("ob.recheck")}</button>
        </Row>
      </Box>
    );
  }

  if (!status.running) {
    return (
      <Box tone="warn">
        <b>{t("ob.notRunning.title")}</b>
        <p style={p}>{t("ob.notRunning.body")}</p>
        <button style={ghost} onClick={refresh}>{t("ob.recheck")}</button>
      </Box>
    );
  }

  if (!hasModel(status.models, model)) {
    return (
      <Box>
        <b>{t("ob.needModel.title")}</b>
        <p style={p}>{t("ob.needModel.body", { model })}</p>
        {pulling ? (
          <>
            <div style={{ height: 8, background: "#eee", borderRadius: 4, overflow: "hidden" }}>
              <div style={{ width: `${pct}%`, height: "100%", background: "#1a1a1a", transition: "width .2s" }} />
            </div>
            <p style={p}>{t("ob.pulling", { pct })}</p>
          </>
        ) : (
          <Row>
            <button style={primary} onClick={onPull}>{t("ob.pull", { model })}</button>
            <button style={ghost} onClick={refresh}>{t("ob.recheck")}</button>
          </Row>
        )}
        {error && <p style={{ ...p, color: "#b3261e" }}>{error}</p>}
      </Box>
    );
  }

  return <Box tone="ok">{t("ob.ready", { model })}</Box>;
}

const p: React.CSSProperties = { fontSize: 12, color: "#555", margin: "6px 0" };
const primary: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "none", background: "#1a1a1a", color: "#fff", cursor: "pointer" };
const ghost: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "1px solid #ddd", background: "#fff", cursor: "pointer" };

function Row({ children }: { children: React.ReactNode }) {
  return <div style={{ display: "flex", gap: 8, marginTop: 8 }}>{children}</div>;
}

function Box({ children, tone }: { children: React.ReactNode; tone?: "warn" | "ok" }) {
  const bg = tone === "warn" ? "#fff6e6" : tone === "ok" ? "#eaf7ee" : "#f6f6f6";
  const fg = tone === "warn" ? "#8a5a00" : tone === "ok" ? "#1a7a3a" : "#333";
  return (
    <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: bg, color: fg, fontSize: 13 }}>
      {children}
    </div>
  );
}
