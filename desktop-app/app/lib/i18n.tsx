"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Locale = "en" | "ko";

// Flat key → { en, ko }. Use {placeholders} for interpolation.
const DICT: Record<string, { en: string; ko: string }> = {
  "app.tagline": { en: "Turn one line into a build-ready spec", ko: "아이디어 한 줄 → 즉시 개발 착수용 기획·설계 문서" },
  "app.booting": { en: "Starting backend…", ko: "백엔드 준비 중…" },
  "app.error": { en: "Something went wrong.", ko: "오류가 발생했습니다." },
  "idea.placeholder": { en: "e.g. A membership SaaS for neighborhood gyms", ko: "예: 동네 헬스장 회원관리 SaaS" },
  "generate.button": { en: "Generate spec", ko: "기획서 생성" },
  "generate.running": { en: "Generating… ({status})", ko: "생성 중… ({status})" },
  "generate.result": { en: "Result: {status}", ko: "생성 결과: {status}" },
  "nav.settings": { en: "Settings", ko: "설정" },

  "settings.title": { en: "Settings · AI engine", ko: "설정 · AI 엔진" },
  "settings.close": { en: "Close", ko: "닫기" },
  "settings.loading": { en: "Loading settings…", ko: "설정 불러오는 중…" },
  "settings.intro": {
    en: "Default is local Ollama (no key, free). For higher quality, enter an Anthropic key.",
    ko: "기본은 로컬 Ollama(키 불필요, 무료). 더 높은 품질을 원하면 Anthropic 키를 입력하세요.",
  },
  "settings.engine": { en: "Engine", ko: "엔진" },
  "settings.engine.ollama": { en: "Ollama (local)", ko: "Ollama (로컬)" },
  "settings.engine.anthropic": { en: "Anthropic (cloud)", ko: "Anthropic (클라우드)" },
  "settings.model": { en: "Model", ko: "모델" },
  "settings.model.installed": { en: "installed: {n}", ko: "설치됨: {n}" },
  "settings.ollama.down": { en: "Ollama isn't running", ko: "Ollama 미실행" },
  "settings.ollama.hint": {
    en: "Ollama isn't running. Install from ollama.com, then run `ollama pull {model}`.",
    ko: "Ollama가 실행 중이 아닙니다. ollama.com 에서 설치 후 `ollama pull {model}` 하세요.",
  },
  "settings.key": { en: "API key", ko: "API 키" },
  "settings.key.saved": { en: "saved: {masked}", ko: "저장됨: {masked}" },
  "settings.key.unset": { en: "not set", ko: "미설정" },
  "settings.key.save": { en: "Save", ko: "저장" },
  "settings.key.note": {
    en: "The key is stored only on this PC (~/.planforge) and never sent anywhere else.",
    ko: "키는 이 PC(~/.planforge)에만 저장되며 외부로 전송되지 않습니다.",
  },
  "settings.saved": { en: "Saved.", ko: "저장됐습니다." },

  // Ollama onboarding
  "ob.checking": { en: "Checking Ollama…", ko: "Ollama 확인 중…" },
  "ob.ready": { en: "✓ Ollama is ready (model: {model})", ko: "✓ Ollama 준비 완료 (모델: {model})" },
  "ob.notInstalled.title": { en: "Ollama isn't installed", ko: "Ollama가 설치되어 있지 않습니다" },
  "ob.notInstalled.body": {
    en: "PlanForge uses Ollama to run a model locally (free, no key). Install it, then come back.",
    ko: "PlanForge는 Ollama로 로컬에서 모델을 돌립니다(무료, 키 불필요). 설치 후 돌아오세요.",
  },
  "ob.install": { en: "Install Ollama", ko: "Ollama 설치" },
  "ob.notRunning.title": { en: "Ollama is installed but not running", ko: "Ollama가 설치됐지만 실행 중이 아닙니다" },
  "ob.notRunning.body": { en: "Start the Ollama app, then re-check.", ko: "Ollama 앱을 실행한 뒤 다시 확인하세요." },
  "ob.recheck": { en: "Re-check", ko: "다시 확인" },
  "ob.needModel.title": { en: "Download a model", ko: "모델 다운로드" },
  "ob.needModel.body": {
    en: "Model \"{model}\" isn't downloaded yet (a few GB, one time).",
    ko: "모델 \"{model}\"이(가) 아직 없습니다 (수 GB, 1회).",
  },
  "ob.pull": { en: "Download {model}", ko: "{model} 다운로드" },
  "ob.pulling": { en: "Downloading… {pct}%", ko: "다운로드 중… {pct}%" },
  "ob.pullDone": { en: "✓ Model downloaded", ko: "✓ 모델 다운로드 완료" },
};

function format(s: string, vars?: Record<string, string | number>): string {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] !== undefined ? String(vars[k]) : `{${k}}`));
}

type Ctx = { locale: Locale; setLocale: (l: Locale) => void; t: (key: string, vars?: Record<string, string | number>) => string };
const I18nContext = createContext<Ctx | null>(null);

const STORAGE_KEY = "planforge.locale";

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    const saved = (typeof localStorage !== "undefined" && localStorage.getItem(STORAGE_KEY)) as Locale | null;
    if (saved === "en" || saved === "ko") setLocaleState(saved);
    else if (typeof navigator !== "undefined" && navigator.language?.startsWith("ko")) setLocaleState("ko");
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    if (typeof localStorage !== "undefined") localStorage.setItem(STORAGE_KEY, l);
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const entry = DICT[key];
      if (!entry) return key;
      return format(entry[locale] ?? entry.en, vars);
    },
    [locale],
  );

  return <I18nContext.Provider value={{ locale, setLocale, t }}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}

/** The Accept-Language value to send to the backend for localized errors. */
export function currentLocale(): Locale {
  if (typeof localStorage === "undefined") return "en";
  const saved = localStorage.getItem(STORAGE_KEY) as Locale | null;
  return saved === "ko" ? "ko" : "en";
}
