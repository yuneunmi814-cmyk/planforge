// Thin client for the bundled FastAPI sidecar (HTTP on 127.0.0.1:PORT).
// The port must match PLANFORGE_PORT passed to the sidecar in src-tauri/src/lib.rs
// and be allow-listed in tauri.conf.json CSP connect-src.

import { currentLocale } from "./i18n";

const PORT = 8000;
export const BASE = `http://localhost:${PORT}`;
export const API = `${BASE}/api/v1`;

// Sent on every request so the backend localizes error messages (KO/EN).
function baseHeaders(): Record<string, string> {
  return { "Content-Type": "application/json", "Accept-Language": currentLocale() };
}

/** Poll /health until the sidecar is up (uvicorn takes ~0.5–2s to boot). */
export async function waitForBackend(timeoutMs = 15000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return true;
    } catch {
      /* not up yet */
    }
    await new Promise((res) => setTimeout(res, 300));
  }
  throw new Error("백엔드가 시간 내에 준비되지 않았습니다.");
}

// --- Local single-user auth bootstrap --------------------------------------
// A desktop app shouldn't ask the user to register. On first launch we create a
// local account (the first user becomes an approved admin) and remember the
// credentials; later launches just log in.
const CRED_KEY = "planforge.localCred";

type Cred = { email: string; password: string };

function loadCred(): Cred {
  const raw = typeof localStorage !== "undefined" ? localStorage.getItem(CRED_KEY) : null;
  if (raw) return JSON.parse(raw);
  const cred: Cred = {
    email: `local-${Math.random().toString(36).slice(2, 10)}@planforge.app`,
    password: Math.random().toString(36).slice(2) + "A1!",
  };
  localStorage.setItem(CRED_KEY, JSON.stringify(cred));
  return cred;
}

let token: string | null = null;

export async function ensureAuth(): Promise<void> {
  if (token) return;
  const cred = loadCred();
  // Try login first; if the account doesn't exist yet, sign up then login.
  let res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: baseHeaders(),
    body: JSON.stringify(cred),
  });
  if (res.status === 401) {
    await fetch(`${API}/auth/signup`, {
      method: "POST",
      headers: baseHeaders(),
      body: JSON.stringify(cred),
    });
    res = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: baseHeaders(),
      body: JSON.stringify(cred),
    });
  }
  const data = await res.json();
  token = data.accessToken;
}

async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  await ensureAuth();
  return fetch(`${API}${path}`, {
    ...init,
    headers: { ...baseHeaders(), Authorization: `Bearer ${token}`, ...(init.headers || {}) },
  });
}

export type Section = { type: string; title: string; markdown: string; version: number };

/** Create a project (async) → returns { projectId, jobId }. */
export async function createProject(idea: string): Promise<{ projectId: number; jobId: number }> {
  const res = await authedFetch("/projects", { method: "POST", body: JSON.stringify({ idea }) });
  if (!res.ok) throw new Error((await res.json())?.error?.message ?? "생성 요청 실패");
  const j = await res.json();
  return { projectId: j.projectId, jobId: j.jobId };
}

/** Poll a job until it reaches a terminal state. */
export async function waitForJob(
  projectId: number,
  jobId: number,
  onStatus?: (s: string) => void,
): Promise<string> {
  for (;;) {
    const res = await authedFetch(`/projects/${projectId}/jobs/${jobId}`);
    const j = await res.json();
    onStatus?.(j.status);
    if (["success", "rejected", "failed"].includes(j.status)) return j.status;
    await new Promise((r) => setTimeout(r, 600));
  }
}

export type ProjectDetail = { sections: Section[]; missingSections: string[] };

export async function getProjectDetail(projectId: number): Promise<ProjectDetail> {
  const res = await authedFetch(`/projects/${projectId}`);
  const j = await res.json();
  return { sections: j.sections ?? [], missingSections: j.missingSections ?? [] };
}

// --- Export (assembled document) -------------------------------------------
export type ExportFormat = "md" | "json";

/** Fetch the assembled document as a string (used for clipboard copy). */
export async function exportText(projectId: number, format: ExportFormat): Promise<string> {
  const res = await authedFetch(`/projects/${projectId}/export?format=${format}`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.error?.message ?? "내보내기 실패");
  return res.text();
}

export type SavedExport = { path: string; filename: string; format: ExportFormat };

/** Write the assembled document to disk via the sidecar; returns its path. */
export async function saveExport(projectId: number, format: ExportFormat): Promise<SavedExport> {
  const res = await authedFetch(`/projects/${projectId}/export/save?format=${format}`, { method: "POST" });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.error?.message ?? "저장 실패");
  return res.json();
}

/** Reveal a previously-saved export in the OS file manager. */
export async function revealExport(projectId: number, format: ExportFormat): Promise<boolean> {
  const res = await authedFetch(`/projects/${projectId}/export/reveal?format=${format}`, { method: "POST" });
  if (!res.ok) return false;
  return (await res.json())?.revealed ?? false;
}

// --- Settings (LLM engine) -------------------------------------------------
export type Settings = {
  llmProvider: "ollama" | "anthropic" | "fake";
  ollamaBaseUrl: string;
  ollamaModel: string;
  anthropicModel: string;
  hasAnthropicKey: boolean;
  anthropicKeyMasked: string;
};

export async function getSettings(): Promise<Settings> {
  const res = await authedFetch("/settings");
  return res.json();
}

export async function updateSettings(patch: Partial<Settings> & { anthropicApiKey?: string }): Promise<Settings> {
  const res = await authedFetch("/settings", { method: "PUT", body: JSON.stringify(patch) });
  if (!res.ok) throw new Error((await res.json())?.error?.message ?? "설정 저장 실패");
  return res.json();
}

export async function listOllamaModels(): Promise<{ available: boolean; models: string[] }> {
  const res = await authedFetch("/settings/ollama/models");
  return res.json();
}

// --- Ollama onboarding -----------------------------------------------------
export type OllamaStatus = {
  installed: boolean;
  running: boolean;
  version?: string;
  models: string[];
  downloadUrl: string;
};

export async function ollamaStatus(): Promise<OllamaStatus> {
  const res = await authedFetch("/settings/ollama/status");
  return res.json();
}

export async function openOllamaDownload(): Promise<void> {
  await authedFetch("/settings/ollama/open-download", { method: "POST" });
}

export type PullProgress = { status: string; completed?: number; total?: number };

/** Pull a model, invoking onProgress for each NDJSON line from Ollama. */
export async function pullOllamaModel(model: string, onProgress: (p: PullProgress) => void): Promise<void> {
  const res = await authedFetch("/settings/ollama/pull", { method: "POST", body: JSON.stringify({ model }) });
  if (!res.ok || !res.body) throw new Error((await res.json().catch(() => null))?.error?.message ?? "pull failed");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (line) {
        try {
          onProgress(JSON.parse(line));
        } catch {
          /* ignore partial/non-JSON */
        }
      }
    }
  }
}
