#!/usr/bin/env node
// Ensure the generated inputs Tauri needs are present before `tauri dev` / `tauri build`.
//
// Two inputs are gitignored (they're produced in CI) so a fresh `git clone` lacks them,
// and the Rust build fails before the app ever launches:
//
//   1. src-tauri/icons/*  — generate_context!() embeds these at compile time. Missing
//      icons => "failed to open icon .../icons/32x32.png: No such file or directory".
//   2. src-tauri/binaries/planforge-backend-<target-triple>  — tauri.conf `externalBin`.
//      Tauri's resource check requires this file to EXIST even for debug builds. Missing
//      => "resource path `binaries/planforge-backend-...` doesn't exist".
//
// dev   : auto-generate icons (from app-icon.png) and a *placeholder* sidecar. The
//         placeholder is never executed in dev — debug builds run the backend from
//         system Python (see src-tauri/src/lib.rs) — it only satisfies the resource check.
// build : auto-generate icons, but REQUIRE a real (non-placeholder) sidecar so we never
//         ship an installer whose bundled backend is a stub.

import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const mode = process.argv[2] === "build" ? "build" : "dev";
const isWindows = process.platform === "win32";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const appDir = resolve(scriptDir, ".."); // desktop-app/
const srcTauri = join(appDir, "src-tauri");
const iconsDir = join(srcTauri, "icons");
const binariesDir = join(srcTauri, "binaries");
const appIcon = join(appDir, "app-icon.png");
const confPath = join(srcTauri, "tauri.conf.json");

// Marker embedded in the placeholder so `build` mode can refuse a stub sidecar.
const STUB_MARKER = "PLANFORGE-DEV-SIDECAR-PLACEHOLDER";
const DEFAULT_ICONS = [
  "icons/32x32.png",
  "icons/128x128.png",
  "icons/128x128@2x.png",
  "icons/icon.icns",
  "icons/icon.ico",
];

const rel = (p) => relative(appDir, p) || p;
const log = (msg) => console.log(`[tauri-prereqs] ${msg}`);
const fail = (msg) => {
  console.error(`\n[tauri-prereqs] ERROR: ${msg}\n`);
  process.exit(1);
};

// tauri.conf.json's bundle.icon is the source of truth for which icons the build needs.
function iconsFromConf() {
  try {
    const conf = JSON.parse(readFileSync(confPath, "utf8"));
    const icons = conf?.bundle?.icon;
    if (Array.isArray(icons) && icons.length) return icons;
  } catch (e) {
    log(`could not read ${rel(confPath)} (${e.message}); using the default icon set`);
  }
  return DEFAULT_ICONS;
}

function tauriBin() {
  // npm puts node_modules/.bin on PATH, but resolve explicitly so this also works
  // when invoked as `node scripts/tauri-prereqs.mjs` directly.
  const local = join(appDir, "node_modules", ".bin", isWindows ? "tauri.cmd" : "tauri");
  return existsSync(local) ? local : "tauri";
}

function ensureIcons() {
  const needed = iconsFromConf().map((r) => join(srcTauri, r));
  const missing = needed.filter((p) => !existsSync(p));
  if (missing.length === 0) {
    log("icons present ✓");
    return;
  }
  if (!existsSync(appIcon)) {
    fail(`icons are missing and the source ${rel(appIcon)} does not exist — cannot generate icons.`);
  }
  log(`icons missing (${missing.length}) → running \`tauri icon app-icon.png\``);
  const bin = tauriBin();
  const res = spawnSync(bin, ["icon", "app-icon.png"], { cwd: appDir, stdio: "inherit" });
  if (res.error) fail(`failed to run the Tauri CLI (${bin}): ${res.error.message}`);
  if (res.status !== 0) fail(`\`tauri icon\` exited with code ${res.status}`);
  // Verify the specific files the build needs actually got created.
  const stillMissing = needed.filter((p) => !existsSync(p)).map(rel);
  if (stillMissing.length) fail(`\`tauri icon\` ran but these are still missing: ${stillMissing.join(", ")}`);
  log("icons generated ✓");
}

function targetTriple() {
  let out;
  try {
    out = execFileSync("rustc", ["-Vv"], { encoding: "utf8" });
  } catch (e) {
    fail(`\`rustc\` not found — install Rust to build the Tauri app (https://tauri.app/start/prerequisites/). (${e.message})`);
  }
  const m = out.match(/^host:\s*(.+)$/m);
  if (!m) fail("could not parse the target triple from `rustc -Vv` output.");
  return m[1].trim();
}

function sidecarPath() {
  return join(binariesDir, `planforge-backend-${targetTriple()}${isWindows ? ".exe" : ""}`);
}

function isStub(p) {
  try {
    return readFileSync(p).includes(STUB_MARKER);
  } catch {
    return false;
  }
}

function ensureDevSidecar() {
  const dest = sidecarPath();
  if (existsSync(dest)) {
    log(`sidecar present (${isStub(dest) ? "dev placeholder" : "real binary"}) ✓`);
    return;
  }
  mkdirSync(binariesDir, { recursive: true });
  const stub = [
    "#!/bin/sh",
    `# ${STUB_MARKER}`,
    "# Not the real backend. Debug builds run the backend from system Python",
    "# (see src-tauri/src/lib.rs); this file exists only to satisfy Tauri's",
    "# externalBin resource check at build time. Build the real PyInstaller",
    "# sidecar for a release installer — see desktop-app/README.md.",
    'echo "planforge-backend: dev placeholder, not a real backend. See desktop-app/README.md to build the PyInstaller sidecar." >&2',
    "exit 1",
    "",
  ].join("\n");
  writeFileSync(dest, stub);
  if (!isWindows) chmodSync(dest, 0o755);
  log(`created dev placeholder sidecar → ${rel(dest)}`);
}

function requireRealSidecar() {
  const dest = sidecarPath();
  if (!existsSync(dest)) {
    fail(
      `sidecar not found: ${rel(dest)}\n` +
        "  Build the real backend before `tauri build`:\n" +
        "    cd ../backend && pip install -r requirements-desktop.txt && pyinstaller planforge-backend.spec\n" +
        `    cp dist/planforge-backend "${dest}" && chmod +x "${dest}"\n` +
        "  (Windows: cp dist/planforge-backend.exe to the same path with a .exe suffix.)\n" +
        "  See desktop-app/README.md → “로컬 프로덕션 빌드”.",
    );
  }
  if (isStub(dest)) {
    fail(
      `sidecar at ${rel(dest)} is a DEV PLACEHOLDER, not the real backend.\n` +
        "  Replace it with the PyInstaller build before `tauri build` — see desktop-app/README.md.",
    );
  }
  log("sidecar present (real binary) ✓");
}

log(`mode: ${mode}`);
ensureIcons();
if (mode === "build") requireRealSidecar();
else ensureDevSidecar();
log("prerequisites ready.");
