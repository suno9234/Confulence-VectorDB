// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashMap;
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::process::Stdio;
use std::sync::{Arc, Mutex};
#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

// 배포 환경: ./python/python.exe 우선, 없으면 시스템 python 폴백
fn resolve_python(cwd: &str) -> String {
    let local = format!("{}\\python\\python.exe", cwd);
    if std::path::Path::new(&local).exists() {
        local
    } else {
        "python".to_string()
    }
}

// ── exe 위치 반환 ─────────────────────────────────────────────────────────────

#[tauri::command]
fn get_exe_dir() -> Result<String, String> {
    std::env::current_exe()
        .map_err(|e| e.to_string())?
        .parent()
        .map(|p| p.to_string_lossy().to_string())
        .ok_or_else(|| "exe 경로를 찾을 수 없습니다".to_string())
}

// ── .env 읽기 ────────────────────────────────────────────────────────────────

#[tauri::command]
fn read_env(path: String) -> Result<HashMap<String, String>, String> {
    let content = std::fs::read_to_string(&path)
        .map_err(|e| format!("파일 읽기 실패: {}", e))?;

    let mut map = HashMap::new();
    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(pos) = line.find('=') {
            let key = line[..pos].trim().to_string();
            let val = line[pos + 1..].trim().to_string();
            if !key.is_empty() {
                map.insert(key, val);
            }
        }
    }
    Ok(map)
}

// ── .env 저장 (주석과 순서 유지) ─────────────────────────────────────────────

#[tauri::command]
fn save_env(path: String, values: HashMap<String, String>) -> Result<(), String> {
    let existing = std::fs::read_to_string(&path).unwrap_or_default();
    let mut lines: Vec<String> = Vec::new();
    let mut updated: std::collections::HashSet<String> = std::collections::HashSet::new();

    for line in existing.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            lines.push(line.to_string());
            continue;
        }
        if let Some(pos) = trimmed.find('=') {
            let key = trimmed[..pos].trim().to_string();
            if let Some(val) = values.get(&key) {
                lines.push(format!("{}={}", key, val));
                updated.insert(key);
            } else {
                lines.push(line.to_string());
            }
        } else {
            lines.push(line.to_string());
        }
    }

    for (key, val) in &values {
        if !updated.contains(key) {
            lines.push(format!("{}={}", key, val));
        }
    }

    std::fs::write(&path, lines.join("\n") + "\n")
        .map_err(|e| format!("파일 저장 실패: {}", e))
}

// ── Python 스크립트 실행 (stdout/stderr 실시간 스트리밍) ──────────────────────

#[tauri::command]
async fn run_python(
    window: tauri::Window,
    script: String,
    cwd: String,
    event_name: String,
) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let python = resolve_python(&cwd);
        let models_dir = format!("{}\\models", cwd);

        let mut child = std::process::Command::new(&python)
            .arg(&script)
            .current_dir(&cwd)
            .env("HF_HOME", &models_dir)
            .env("SENTENCE_TRANSFORMERS_HOME", &models_dir)
            .env("HF_HUB_OFFLINE", "1")
            .env("TRANSFORMERS_OFFLINE", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| format!("Python 실행 실패: {}", e))?;

        let stdout = child.stdout.take().unwrap();
        let stderr = child.stderr.take().unwrap();

        let w1 = window.clone();
        let e1 = event_name.clone();
        let t1 = std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines().flatten() {
                let _ = w1.emit(&e1, &line);
            }
        });

        let w2 = window.clone();
        let e2 = event_name.clone();
        let t2 = std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().flatten() {
                if line.contains("telemetry") { continue; }
                let _ = w2.emit(&e2, format!("[ERR] {}", line));
            }
        });

        let _ = child.wait();
        let _ = t1.join();
        let _ = t2.join();
        let _ = window.emit(&event_name, "__DONE__");

        Ok::<(), String>(())
    })
    .await
    .map_err(|e| e.to_string())?
}

// ── 컬렉션 목록 조회 ─────────────────────────────────────────────────────────

#[tauri::command]
async fn list_collections(cwd: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let python = resolve_python(&cwd);
        let models_dir = format!("{}\\models", cwd);

        let output = std::process::Command::new(&python)
            .arg("backend/search_once.py")
            .arg("--list")
            .current_dir(&cwd)
            .env("HF_HOME", &models_dir)
            .env("SENTENCE_TRANSFORMERS_HOME", &models_dir)
            .env("HF_HUB_OFFLINE", "1")
            .env("TRANSFORMERS_OFFLINE", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map_err(|e| format!("실행 실패: {}", e))?;

        String::from_utf8(output.stdout).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

// ── 컬렉션 삭제 ──────────────────────────────────────────────────────────────

#[tauri::command]
async fn delete_collection(cwd: String, collection: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let python = resolve_python(&cwd);
        let models_dir = format!("{}\\models", cwd);

        let output = std::process::Command::new(&python)
            .arg("backend/search_once.py")
            .arg("--delete")
            .arg(&collection)
            .current_dir(&cwd)
            .env("HF_HOME", &models_dir)
            .env("SENTENCE_TRANSFORMERS_HOME", &models_dir)
            .env("HF_HUB_OFFLINE", "1")
            .env("TRANSFORMERS_OFFLINE", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map_err(|e| format!("실행 실패: {}", e))?;

        String::from_utf8(output.stdout).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

// ── 검색 (search_once.py 호출 → JSON 반환) ───────────────────────────────────

#[tauri::command]
async fn run_search(query: String, cwd: String, top_k: u32, collection: String, alpha: f64) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let python = resolve_python(&cwd);
        let models_dir = format!("{}\\models", cwd);

        let output = std::process::Command::new(&python)
            .arg("backend/search_once.py")
            .arg(&query)
            .arg(top_k.to_string())
            .arg(&collection)
            .arg(alpha.to_string())
            .current_dir(&cwd)
            .env("HF_HOME", &models_dir)
            .env("SENTENCE_TRANSFORMERS_HOME", &models_dir)
            .env("HF_HUB_OFFLINE", "1")
            .env("TRANSFORMERS_OFFLINE", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map_err(|e| format!("검색 실행 실패: {}", e))?;

        String::from_utf8(output.stdout).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

// ── 챗봇 상주 서버 상태 ───────────────────────────────────────────────────────

struct ChatProcess {
    stdin:  BufWriter<std::process::ChildStdin>,
    stdout: BufReader<std::process::ChildStdout>,
    child:  std::process::Child,
}

#[derive(Clone)]
struct ChatState(Arc<Mutex<Option<ChatProcess>>>);

// ── 챗봇 서버 시작 (모델 로드 완료까지 대기) ──────────────────────────────────

#[tauri::command]
async fn start_chat_server(
    state: tauri::State<'_, ChatState>,
    cwd: String,
) -> Result<String, String> {
    let arc = Arc::clone(&state.0);
    tauri::async_runtime::spawn_blocking(move || {
        let mut guard = arc.lock().map_err(|e| e.to_string())?;

        // 이미 살아있으면 스킵 (has_history 없이 빈 JSON 반환)
        if let Some(ref mut chat) = *guard {
            if chat.child.try_wait().map_err(|e| e.to_string())?.is_none() {
                return Ok("{}".to_string());
            }
        }

        let python     = resolve_python(&cwd);
        let models_dir = format!("{}\\models", cwd);

        let mut child = std::process::Command::new(&python)
            .arg("backend/chat_server.py")
            .arg(&cwd)  // cwd를 인자로 전달 → 히스토리 파일 경로 결정에 사용
            .current_dir(&cwd)
            .env("HF_HOME", &models_dir)
            .env("SENTENCE_TRANSFORMERS_HOME", &models_dir)
            .env("HF_HUB_OFFLINE", "1")
            .env("TRANSFORMERS_OFFLINE", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| format!("챗봇 서버 시작 실패: {}", e))?;

        let stdin  = child.stdin.take().unwrap();
        let stdout = child.stdout.take().unwrap();

        // stderr는 별도 스레드에서 드레인 (텔레메트리 제외)
        if let Some(stderr) = child.stderr.take() {
            std::thread::spawn(move || {
                for line in BufReader::new(stderr).lines().flatten() {
                    if !line.contains("telemetry") {
                        eprintln!("[chat_server] {}", line);
                    }
                }
            });
        }

        let mut chat = ChatProcess {
            stdin:  BufWriter::new(stdin),
            stdout: BufReader::new(stdout),
            child,
        };

        // {"status": "ready", "has_history": ..., "turns": ...} 수신까지 대기
        let mut ready_line = String::new();
        let mut line = String::new();
        loop {
            line.clear();
            if chat.stdout.read_line(&mut line).unwrap_or(0) == 0 { break; }
            if line.contains("\"ready\"") {
                ready_line = line.trim().to_string();
                break;
            }
        }

        *guard = Some(chat);
        Ok::<String, String>(ready_line)
    })
    .await
    .map_err(|e| e.to_string())?
}

// ── 챗봇 메시지 전송 (stdin → stdout 스트리밍) ───────────────────────────────

#[tauri::command]
async fn send_chat_message(
    window: tauri::Window,
    state: tauri::State<'_, ChatState>,
    question: String,
    collection: String,
    top_k: u32,
    alpha: f64,
) -> Result<(), String> {
    let arc = Arc::clone(&state.0);
    tauri::async_runtime::spawn_blocking(move || {
        let mut guard = arc.lock().map_err(|e| e.to_string())?;
        let chat = guard.as_mut()
            .ok_or("챗봇 서버가 실행되지 않았습니다.")?;

        if chat.child.try_wait().map_err(|e| e.to_string())?.is_some() {
            return Err("챗봇 서버가 종료되었습니다. 앱을 재시작하세요.".to_string());
        }

        // 질문 전송
        let msg = serde_json::json!({
            "question":   question,
            "collection": collection,
            "top_k":      top_k,
            "alpha":      alpha,
        });
        writeln!(chat.stdin, "{}", msg).map_err(|e| e.to_string())?;
        chat.stdin.flush().map_err(|e| e.to_string())?;

        // 응답 스트리밍
        let mut line = String::new();
        loop {
            line.clear();
            if chat.stdout.read_line(&mut line).map_err(|e| e.to_string())? == 0 { break; }
            let trimmed = line.trim();
            if trimmed.is_empty() { continue; }
            let _ = window.emit("chat_output", trimmed);
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(trimmed) {
                if v.get("done").and_then(|d| d.as_bool()).unwrap_or(false) { break; }
            }
        }
        Ok::<(), String>(())
    })
    .await
    .map_err(|e| e.to_string())?
}

// ── 대화 히스토리 초기화 ─────────────────────────────────────────────────────

#[tauri::command]
async fn reset_chat_history(
    state: tauri::State<'_, ChatState>,
) -> Result<(), String> {
    let arc = Arc::clone(&state.0);
    tauri::async_runtime::spawn_blocking(move || {
        let mut guard = arc.lock().map_err(|e| e.to_string())?;
        let chat = guard.as_mut()
            .ok_or("챗봇 서버가 실행되지 않았습니다.")?;

        writeln!(chat.stdin, "{{\"cmd\":\"reset\"}}").map_err(|e| e.to_string())?;
        chat.stdin.flush().map_err(|e| e.to_string())?;

        let mut line = String::new();
        loop {
            line.clear();
            if chat.stdout.read_line(&mut line).unwrap_or(0) == 0 { break; }
            if line.contains("\"done\"") { break; }
        }
        Ok::<(), String>(())
    })
    .await
    .map_err(|e| e.to_string())?
}

// ── 메인 ─────────────────────────────────────────────────────────────────────

fn main() {
    tauri::Builder::default()
        .manage(ChatState(Arc::new(Mutex::new(None))))
        .invoke_handler(tauri::generate_handler![
            get_exe_dir,
            read_env,
            save_env,
            run_python,
            run_search,
            list_collections,
            delete_collection,
            start_chat_server,
            send_chat_message,
            reset_chat_history,
        ])
        .run(tauri::generate_context!())
        .expect("Tauri 앱 실행 오류");
}
