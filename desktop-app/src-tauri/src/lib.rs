//! PlanForge Tauri shell.
//!
//! Because the backend is a plain HTTP service (FastAPI), we don't need Meetily's
//! pipe-based SidecarManager. We just spawn the backend on startup and kill it on
//! exit via `tauri-plugin-shell`.
//!
//! dev  : run the backend from system Python (fast iteration, no PyInstaller build)
//! prod : run the bundled PyInstaller sidecar registered in tauri.conf `externalBin`

use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const BACKEND_PORT: &str = "8000";

/// Holds the backend child so we can terminate it when the app exits.
struct Backend(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            let shell = app.shell();

            let command = if cfg!(debug_assertions) {
                // dev: import the backend package via uvicorn --app-dir (../../backend
                // relative to src-tauri). Run uvicorn from the active venv's python.
                shell
                    .command("python")
                    .args([
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--app-dir",
                        "../../backend",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        BACKEND_PORT,
                    ])
                    .env("PLANFORGE_INLINE_DISPATCH", "true")
            } else {
                // prod: the bundled sidecar (name matches externalBin in tauri.conf).
                shell
                    .sidecar("planforge-backend")
                    .expect("사이드카 바이너리를 찾을 수 없습니다")
                    .env("PLANFORGE_PORT", BACKEND_PORT)
                    .env("PLANFORGE_INLINE_DISPATCH", "true")
            };

            let (mut rx, child) = command.spawn().expect("백엔드 기동 실패");
            app.state::<Backend>().0.lock().unwrap().replace(child);

            // Forward backend logs to the app's stderr for debugging.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                            eprintln!("[backend] {}", String::from_utf8_lossy(&line));
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            // Kill the backend when the app is asked to exit (avoid zombie process).
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(child) = app.state::<Backend>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
