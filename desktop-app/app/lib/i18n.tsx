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
  "generate.partial": {
    en: "This model produced only {got} of {total} sections. For the full document, pick a larger Ollama model or switch to Anthropic in Settings.",
    ko: "이 모델은 {total}개 중 {got}개 섹션만 생성했습니다. 전체 문서를 보려면 더 큰 Ollama 모델을 쓰거나 설정에서 Anthropic으로 전환하세요.",
  },
  "nav.settings": { en: "Settings", ko: "설정" },

  // Export / download
  "export.copy": { en: "Copy Markdown", ko: "마크다운 복사" },
  "export.saveMd": { en: "Save .md", ko: ".md로 저장" },
  "export.saveJson": { en: "Save .json", ko: ".json으로 저장" },
  "export.copied": { en: "Copied to clipboard.", ko: "클립보드에 복사했습니다." },
  "export.copyFailed": { en: "Couldn't copy — use Save instead.", ko: "복사하지 못했습니다 — 저장을 이용하세요." },
  "export.saved": { en: "Saved to {path}", ko: "{path} 에 저장했습니다" },
  "export.reveal": { en: "Show in folder", ko: "폴더에서 보기" },
  "export.failed": { en: "Export failed: {msg}", ko: "내보내기 실패: {msg}" },

  // Manual handoff (bring your own ChatGPT/Claude/Gemini)
  "manual.toggle": {
    en: "Or — use your own ChatGPT / Claude / Gemini (no API key)",
    ko: "또는 — 키 없이 내 ChatGPT·Claude·Gemini로 직접 (구독 활용)",
  },
  "manual.hide": { en: "Hide manual mode", ko: "직접 모드 닫기" },
  "manual.intro": {
    en: "Copy the prompt, paste it into your own chat (where you're already subscribed), then paste the reply back here — PlanForge parses it into the 9 sections. No key, no extra cost.",
    ko: "프롬프트를 복사해 (이미 구독 중인) 내 챗에 붙여넣고, 받은 답변을 여기 다시 붙여넣으면 PlanForge가 9개 섹션으로 정리합니다. 키도 추가 비용도 없습니다.",
  },
  "manual.copyPrompt": { en: "1) Copy prompt", ko: "1) 프롬프트 복사" },
  "manual.openIn": { en: "open in:", ko: "또는 열기:" },
  "manual.pastePlaceholder": {
    en: "2) Paste the model's full reply (the JSON) here",
    ko: "2) 모델 응답(JSON 전체)을 여기에 붙여넣으세요",
  },
  "manual.import": { en: "3) Import result", ko: "3) 결과 가져오기" },
  "manual.copied": {
    en: "Prompt copied — paste it into your chat, then bring the reply back here.",
    ko: "프롬프트를 복사했습니다 — 챗에 붙여넣고 결과를 받아 다시 붙여넣으세요.",
  },
  "manual.importing": { en: "Importing…", ko: "가져오는 중…" },
  "manual.rejected": { en: "The model rejected this: {reason}", ko: "모델이 거부했습니다: {reason}" },
  "manual.failed": { en: "Failed: {msg}", ko: "실패: {msg}" },

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
  "settings.engine.openai": { en: "OpenAI", ko: "OpenAI" },
  "settings.engine.gemini": { en: "Gemini", ko: "Gemini" },
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
  "settings.key.apiNote": {
    en: "An API key (from the provider's developer console) — this is billed per token and is separate from a ChatGPT/Gemini subscription. Stored only on this PC.",
    ko: "개발자 콘솔에서 발급하는 API 키입니다. 토큰당 과금되며 ChatGPT·Gemini 구독과는 별개예요. 이 PC에만 저장됩니다.",
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
