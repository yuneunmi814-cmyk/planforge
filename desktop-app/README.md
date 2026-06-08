# PlanForge Desktop (Tauri + FastAPI 사이드카)

Meetily와 같은 구조: **Tauri 셸**(네이티브 창) + **PyInstaller로 묶은 FastAPI 백엔드**(사이드카, HTTP).
앱을 켜면 백엔드가 `127.0.0.1:8000`에 자동으로 뜨고, 닫으면 함께 종료됩니다.
백엔드는 로컬 단독 모드(`INLINE_DISPATCH`+SQLite, Redis 불필요)로 돕니다.

## 다국어 (KO / EN 토글)

우상단 토글로 언어 전환(브라우저 언어 자동감지 + `localStorage` 저장). 프론트 문자열은 `app/lib/i18n.tsx` 사전에서, **백엔드 에러 메시지는 `Accept-Language` 헤더**로 현지화됩니다(기본 영어). 새 문자열은 사전에 `{en, ko}`로 추가하면 됩니다.

## AI 엔진 (Meetily처럼 로컬 우선)

- **기본: Ollama (로컬, 키 불필요)** — 사용자가 [ollama.com](https://ollama.com) 설치 후 `ollama pull llama3.1` 한 번 하면 **키·비용 없이** 동작.
- **선택: Anthropic (클라우드, 고품질)** — 앱 내 **⚙ 설정** 화면에서 API 키를 입력하면 Claude 사용. 키는 `~/.planforge/config.json`에만 저장(외부 전송 없음).
- 엔진/모델/키는 런타임에 설정 화면에서 변경(`/api/v1/settings`). 변경 즉시 다음 생성부터 적용.

> 참고: Claude 같은 클라우드 모델은 앱에 번들할 수 없어(수천억 파라미터) 키가 필요합니다.
> whisper처럼 로컬에서 돌릴 수 있는 모델은 Ollama로 대체합니다.

```
desktop/planforge/
├── backend/                 # FastAPI (이 앱이 번들하는 대상)
│   ├── run_desktop.py       # 사이드카 진입점 (포트/DB/프롬프트 자동설정)
│   └── planforge-backend.spec  # PyInstaller (prompts/ 동봉)
└── desktop-app/             # ← 이 폴더 (Tauri + Next.js)
    ├── app/                 # Next.js 프론트 (output: 'export' → out/)
    ├── app-icon.png         # 아이콘 원본 (tauri icon 입력)
    └── src-tauri/           # Rust 셸
        ├── tauri.conf.json  # externalBin / CSP / bundle targets
        ├── src/lib.rs       # 사이드카 spawn + dev/prod 분기 + 종료 정리
        └── binaries/        # planforge-backend-<triple> (빌드 시 생성)
```

## 사전 준비 (1회)

- **Node 18+** / **npm**
- **Rust** (stable) + **Tauri 시스템 의존성** — https://tauri.app/start/prerequisites/
- **Python 3.12** (사이드카 빌드용)

## 개발 실행 (빠른 반복)

dev 모드는 PyInstaller 없이 **시스템 파이썬으로 백엔드를 직접** 띄웁니다(`src-tauri/src/lib.rs`의 분기).

```bash
cd desktop/planforge/desktop-app
npm install

# 백엔드가 import되도록 파이썬 의존성 준비(상위 backend 기준)
#   pip install -r ../backend/requirements.txt
npm run tauri:dev
```

> dev는 `python -m uvicorn app.main:app --app-dir ../../backend` 를 자동 실행합니다.
> 파이썬/venv가 PATH에 잡혀 있어야 합니다(필요시 venv 활성화 후 실행).

## 로컬 프로덕션 빌드 (.dmg / .exe 만들기)

```bash
# 1) 백엔드를 단일 실행파일로
cd desktop/planforge/backend
pip install -r requirements-desktop.txt
pyinstaller planforge-backend.spec      # → dist/planforge-backend

# 2) Tauri가 찾는 이름(타깃 트리플 접미사)으로 복사  ★ 함정 1순위
TRIPLE=$(rustc -Vv | sed -n 's/host: //p')
mkdir -p ../desktop-app/src-tauri/binaries
cp dist/planforge-backend "../desktop-app/src-tauri/binaries/planforge-backend-$TRIPLE"
#   (Windows: dist/planforge-backend.exe → ...-$TRIPLE.exe)

# 3) 아이콘 생성 + 앱 빌드
cd ../desktop-app
npm install
npm run tauri icon app-icon.png         # → src-tauri/icons/*
npm run tauri:build                      # → src-tauri/target/release/bundle/
```

산출물: macOS `…/bundle/dmg/*.dmg`, Windows `…/bundle/nsis/*-setup.exe`.

## GitHub Releases 배포 (자동)

`.github/workflows/planforge-desktop-release.yml` 가 위 과정을 mac(arm/intel)·win에서 자동 수행합니다.

```bash
git tag pf-v0.1.0
git push origin pf-v0.1.0
```

→ Actions가 사이드카 빌드 → 트리플 접미사 복사 → 아이콘 생성 → `tauri build` → **Release(초안)에 .dmg/.exe 업로드**.
초안을 확인하고 publish 하면 사용자가 Releases에서 받아 설치합니다.

## 서명/공증 (배포 품질)

- **macOS**: 공증(notarization) 없으면 "확인되지 않은 개발자" 경고 → 사용자가 **우클릭 → 열기**로 우회. 정식 배포는 Apple Developer($99/년) 인증서로 워크플로의 `APPLE_*` 시크릿을 채우면 자동 서명·공증됩니다.
- **Windows**: 코드사인 없으면 SmartScreen 경고. EV/OV 인증서로 서명 권장.

## 자동 업데이트 (선택, 추후)

Tauri updater는 의도적으로 비활성 상태입니다. 켜려면:
1. `npm run tauri signer generate` 로 키 생성
2. 공개키 → `tauri.conf.json`의 `plugins.updater.pubkey`, 비밀키 → GitHub Secrets
3. `bundle.createUpdaterArtifacts: true` + `latest.json` 엔드포인트 설정

## 핵심 주의사항 (참고자료에서)

- **externalBin 네이밍**: 반드시 `planforge-backend-<target-triple>`(Windows는 `.exe`). 안 맞으면 빌드 시 사이드카를 못 찾음.
- **CSP `connect-src`**: `tauri.conf.json`에 `http://localhost:8000`(+필요시 Ollama `:11434`)을 열어둬야 프론트의 `fetch`가 막히지 않음.
- **헬스체크**: 프론트 진입 시 `waitForBackend()`(`app/lib/backend.ts`)가 `/health`를 폴링해 uvicorn 부팅(0.5~2초) 깜빡임을 방지.
