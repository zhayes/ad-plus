// OpenMontage desktop shell.
//
// Tauri 2 window that hosts the local Python backend:
//   1. reuse a backend already answering on 127.0.0.1:8765, or spawn
//      `python -u -m app.main --no-window` from the repo;
//   2. wait for /api/health;
//   3. open a WKWebView window on it;
//   4. kill the child we own when the window closes.

use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::menu::{MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder};
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

const PORT: u16 = 8765;
const TITLE: &str = "";  // no text in the title bar; the icon carries the brand

struct BackendChild(Mutex<Option<Child>>);

fn looks_like_workspace(path: &std::path::Path) -> bool {
    path.join("adplus").join("paths.py").is_file() && path.join("app").join("main.py").is_file()
}

/// Workspace root: env override → walk up from the executable (portable
/// bundle: any extraction dir) → compile-time dev layout.
fn repo_root() -> std::path::PathBuf {
    for key in ["ADPLUS_HOME", "OPENMONTAGE_REPO"] {
        if let Ok(value) = std::env::var(key) {
            return std::path::PathBuf::from(value);
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        for ancestor in exe.ancestors() {
            if looks_like_workspace(ancestor) {
                return ancestor.to_path_buf();
            }
        }
    }

    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .canonicalize()
        .unwrap_or_else(|_| std::path::PathBuf::from("."))
}

fn healthy() -> bool {
    let url = format!("http://127.0.0.1:{PORT}/api/health");
    match ureq_get(&url) {
        Some(body) => body.contains("\"ok\":true") || body.contains("\"ok\": true"),
        None => false,
    }
}

fn ureq_get(url: &str) -> Option<String> {
    use std::io::{Read, Write};
    let addr = url.trim_start_matches("http://");
    let (host_port, path) = addr.split_once('/').map(|(h, p)| (h, format!("/{p}")))?;
    let mut stream = std::net::TcpStream::connect(host_port).ok()?;
    stream.set_read_timeout(Some(Duration::from_millis(1500))).ok()?;
    write!(
        stream,
        "GET {path} HTTP/1.1\r\nHost: {host_port}\r\nConnection: close\r\n\r\n"
    )
    .ok()?;
    let mut raw = String::new();
    stream.read_to_string(&mut raw).ok()?;
    raw.split("\r\n\r\n").nth(1).map(|body| body.to_string())
}

fn spawn_backend() -> Option<Child> {
    let repo = repo_root();
    let python = repo.join(".venv").join("bin").join("python");
    let exe = if python.exists() {
        python
    } else {
        std::path::PathBuf::from("python3")
    };
    let mut cmd = Command::new(exe);
    cmd.args([
        "-u",
        "-m",
        "app.main",
        "--no-window",
        "--port",
        &PORT.to_string(),
        "--parent-pid",
        &std::process::id().to_string(),
    ])
        .current_dir(&repo)
        .env("PATH", format!("{}/.local/bin:{}", std::env::var("HOME").unwrap_or_default(), std::env::var("PATH").unwrap_or_default()));
    cmd.spawn().ok()
}

fn wait_for_health(deadline: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < deadline {
        if healthy() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

fn already_running() -> bool {
    // Hold a loopback port as a singleton token: a second launch cannot bind
    // it, so it exits instead of starting a second backend and window.
    match std::net::TcpListener::bind(("127.0.0.1", 8799)) {
        Ok(listener) => {
            // Keep the listener alive for the process lifetime.
            std::mem::forget(listener);
            false
        }
        Err(_) => true,
    }
}

fn main() {
    if already_running() {
        eprintln!("Ad+ is already running");
        return;
    }
    tauri::Builder::default()
        .manage(BackendChild(Mutex::new(None)))
        .on_menu_event(|app, event| {
            let id = event.id().0.clone();
            if let Some(win) = app.get_webview_window("main") {
                let script = format!(
                    "window.dispatchEvent(new CustomEvent('adplus-menu', {{ detail: {id:?} }}))"
                );
                let _ = win.eval(&script);
            }
        })
        .setup(|app| {
            let app_menu = SubmenuBuilder::new(app, "Ad+")
                .item(&MenuItemBuilder::with_id("about", "关于 Ad+").build(app)?)
                .separator()
                .item(&MenuItemBuilder::with_id("open-settings", "设置…").build(app)?)
                .separator()
                .item(&PredefinedMenuItem::quit(app, None)?)
                .build()?;
            let file_menu = SubmenuBuilder::new(app, "文件")
                .item(&MenuItemBuilder::with_id("new-project", "新建项目").accelerator("CmdOrCtrl+N").build(app)?)
                .item(&MenuItemBuilder::with_id("open-projects", "打开项目").accelerator("CmdOrCtrl+O").build(app)?)
                .separator()
                .item(&MenuItemBuilder::with_id("command-palette", "命令面板").accelerator("CmdOrCtrl+K").build(app)?)
                .build()?;
            let view_menu = SubmenuBuilder::new(app, "视图")
                .item(&MenuItemBuilder::with_id("open-studio", "制作").build(app)?)
                .item(&MenuItemBuilder::with_id("open-assets", "资产").build(app)?)
                .item(&MenuItemBuilder::with_id("open-tasks", "任务").build(app)?)
                .build()?;
            let help_menu = SubmenuBuilder::new(app, "帮助")
                .item(&MenuItemBuilder::with_id("shortcuts", "快捷键").build(app)?)
                .build()?;
            let menu = MenuBuilder::new(app)
                .item(&app_menu)
                .item(&file_menu)
                .item(&view_menu)
                .item(&help_menu)
                .build()?;
            app.set_menu(menu)?;


            // Show the embedded splash immediately: no blank window while the
            // Python backend imports ~200 tool modules.
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title(TITLE)
                .inner_size(1180.0, 840.0)
                .min_inner_size(960.0, 680.0)
                .background_color(tauri::window::Color(11, 12, 16, 255))
                .build()?;

            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let reuse = healthy();
                if !reuse {
                    let child = spawn_backend();
                    if let Some(child) = child {
                        *handle.state::<BackendChild>().0.lock().unwrap() = Some(child);
                    }
                }
                let ready = wait_for_health(Duration::from_secs(90));
                if let Some(win) = handle.get_webview_window("main") {
                    if ready {
                        let url = format!("http://127.0.0.1:{PORT}/");
                        match url.parse() {
                            Ok(parsed) => {
                                let _ = win.navigate(parsed);
                            }
                            Err(err) => eprintln!("bad backend url: {err}"),
                        }
                    } else {
                        eprintln!("backend not healthy after 90s (reuse={reuse})");
                        let _ = win.eval("document.body.innerHTML='<p style=\'color:#e8eaf0;font:14px -apple-system;padding:40px\'>后端没有启动成功，请查看 ~/Library/Application Support/Ad+/app.log</p>'");
                    }
                }
            });
            let _ = window;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build OpenMontage shell")
        .run(|app, event| {
            if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
                if let Some(mut child) = app.state::<BackendChild>().0.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}
