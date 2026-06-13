# GitHub Discoverability — paste-ready

How people find PlanForge on GitHub = repo **name** + **About description** + **topics** + a good
**README** + **Releases**. Below is copy/paste-ready content.

## 1. Repo "About" description (Settings → top-right ⚙ on the repo page)

```
Turn a one-line idea into a build-ready product spec. Local-first desktop app (Tauri + FastAPI) with Ollama or Anthropic. KO/EN.
```

## 2. Topics (Settings → Topics)

```
ai, ai-agent, llm, tauri, fastapi, desktop-app, ollama, anthropic, claude,
product-management, spec-generator, planning, local-first, nextjs, rust, python
```

## 3. Set them via gh CLI (optional)

```bash
gh repo edit <owner>/<repo> \
  --description "Turn a one-line idea into a build-ready product spec. Local-first desktop app (Tauri + FastAPI) with Ollama or Anthropic. KO/EN." \
  --add-topic ai --add-topic ai-agent --add-topic llm --add-topic tauri \
  --add-topic fastapi --add-topic desktop-app --add-topic ollama \
  --add-topic anthropic --add-topic local-first --add-topic spec-generator
```

## 4. First release (triggers the build → installers on Releases)

```bash
git tag pf-v0.1.0
git push origin pf-v0.1.0
# GitHub Actions builds macOS + Windows installers and creates a DRAFT release.
# Review the draft, paste the notes below, then Publish.
```

### Release notes template

```markdown
## PlanForge v0.1.0

One-line idea → full, build-ready product spec. Runs locally.

### Install
- macOS: download the `.dmg` (right-click → Open on first launch — unsigned build)
- Windows: download the `-setup.exe` (More info → Run anyway on first launch)

### First run
Pick an AI engine in ⚙ Settings:
- **Ollama** (local, free): install ollama.com, then `ollama pull llama3.1`
- **Anthropic** (cloud): paste your API key (stored locally)

### Highlights
- 13-section spec generation with live progress
- Per-section refine, Markdown/JSON export
- KO/EN toggle
```

## 5. Recommended: make PlanForge its own repo

For real discoverability, PlanForge should be a **standalone repo** (this monorepo's root README is a
different product). Two clean options:

- **Fresh repo (simplest):** copy `desktop/planforge/*` into a new repo named `planforge`, keep this
  `README.md` at its root, move the workflow to `.github/workflows/` and drop the `working-directory:
  desktop/planforge` defaults + path prefixes.
- **Preserve history:** `git subtree split --prefix=desktop/planforge -b planforge-only`, then push
  that branch to the new repo.

Either way: repo name `planforge`, add the description + topics above, add a screenshot at
`docs/screenshot.png`, and cut the first `pf-v*` (or `v*`) release.

## 6. Nice-to-haves for trust/reach
- Code-sign + notarize (removes the unsigned warnings) — Apple Developer ($99/yr), Windows cert.
- A 10–20s demo GIF in the README.
- Submit to relevant "awesome" lists (awesome-tauri, awesome-ai-agents).
```
