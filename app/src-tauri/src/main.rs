// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::process::Stdio;

// 배포 환경: ./python/python.exe 우선, 없으면 시스템 python 폴백
fn resolve_python(cwd: &str) -> String {
    let local = format!("{}\\python\\python.exe", cwd);
    if std::path::Path::new(&local).exists() {
        local
    } else {
        "python".to_string()
    }
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
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
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

// ── 검색 (search_once.py 호출 → JSON 반환) ───────────────────────────────────

#[tauri::command]
async fn run_search(query: String, cwd: String, top_k: u32) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let python = resolve_python(&cwd);
        let models_dir = format!("{}\\models", cwd);

        let output = std::process::Command::new(&python)
            .arg("backend/search_once.py")
            .arg(&query)
            .arg(top_k.to_string())
            .current_dir(&cwd)
            .env("HF_HOME", &models_dir)
            .env("SENTENCE_TRANSFORMERS_HOME", &models_dir)
            .output()
            .map_err(|e| format!("검색 실행 실패: {}", e))?;

        String::from_utf8(output.stdout).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

// ── 메인 ─────────────────────────────────────────────────────────────────────

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            read_env,
            save_env,
            run_python,
            run_search,
        ])
        .run(tauri::generate_context!())
        .expect("Tauri 앱 실행 오류");
}
