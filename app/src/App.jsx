import { useState, useEffect, useRef } from 'react'
import { invoke } from '@tauri-apps/api/tauri'
import { listen } from '@tauri-apps/api/event'
import { open } from '@tauri-apps/api/dialog'

const ENV_FIELDS = [
  { key: 'CONFLUENCE_BASE_URL',   label: 'Confluence URL',   placeholder: 'https://your-domain.atlassian.net' },
  { key: 'CONFLUENCE_EMAIL',      label: '이메일',            placeholder: 'your@email.com' },
  { key: 'CONFLUENCE_API_TOKEN',  label: 'API 토큰',          placeholder: 'your_api_token', type: 'password' },
  { key: 'CONFLUENCE_SPACE_KEY',  label: 'Space Key',         placeholder: 'NAW' },
  { key: 'ROOT_PAGE_ID',          label: '루트 페이지 ID',     placeholder: '622768' },
  { key: 'EMBEDDING_MODEL',       label: '임베딩 모델',        placeholder: 'jhgan/ko-sroberta-multitask' },
  { key: 'VECTOR_DB_PATH',        label: 'Vector DB 경로',    placeholder: './vector_db' },
  { key: 'VECTOR_DB_COLLECTION',  label: '컬렉션 이름',        placeholder: 'confluence' },
  { key: 'CHUNK_SIZE',            label: '청크 크기 (글자)',   placeholder: '500' },
  { key: 'CHUNK_OVERLAP',         label: '청크 오버랩 (글자)', placeholder: '50' },
]

export default function App() {
  const [tab, setTab]               = useState('settings')
  const [projectDir, setProjectDir] = useState(() => localStorage.getItem('projectDir') || '')
  const [env, setEnv]               = useState({})
  const [saveMsg, setSaveMsg]       = useState('')
  const [running, setRunning]       = useState(false)
  const [output, setOutput]         = useState([])
  const [query, setQuery]           = useState('')
  const [topK, setTopK]             = useState(5)
  const [searching, setSearching]   = useState(false)
  const [results, setResults]       = useState([])
  const [searchErr, setSearchErr]   = useState('')
  const outputRef = useRef(null)

  useEffect(() => {
    if (projectDir) loadEnv()
  }, [projectDir])

  useEffect(() => {
    if (outputRef.current)
      outputRef.current.scrollTop = outputRef.current.scrollHeight
  }, [output])

  async function pickDir() {
    const dir = await open({ directory: true, title: '프로젝트 폴더 선택' })
    if (!dir) return
    setProjectDir(dir)
    localStorage.setItem('projectDir', dir)
  }

  async function loadEnv() {
    try {
      const data = await invoke('read_env', { path: `${projectDir}/.env` })
      setEnv(data)
    } catch (e) {
      console.error(e)
    }
  }

  async function saveEnv() {
    try {
      await invoke('save_env', { path: `${projectDir}/.env`, values: env })
      setSaveMsg('✓ 저장됨')
      setTimeout(() => setSaveMsg(''), 2000)
    } catch (e) {
      alert(e)
    }
  }

  async function runScript(script) {
    if (!projectDir) return alert('프로젝트 폴더를 먼저 선택하세요')
    if (running) return
    setRunning(true)
    setOutput([`▶  python ${script}`])

    const unlisten = await listen('script_output', (event) => {
      if (event.payload === '__DONE__') {
        setRunning(false)
        setOutput(prev => [...prev, '', '✓  완료'])
        unlisten()
      } else {
        setOutput(prev => [...prev, event.payload])
      }
    })

    try {
      await invoke('run_python', { script, cwd: projectDir, eventName: 'script_output' })
    } catch (e) {
      setOutput(prev => [...prev, `오류: ${e}`])
      setRunning(false)
      unlisten()
    }
  }

  async function doSearch() {
    if (!projectDir) return alert('프로젝트 폴더를 먼저 선택하세요')
    if (!query.trim() || searching) return
    setSearching(true)
    setResults([])
    setSearchErr('')
    try {
      const raw  = await invoke('run_search', { query: query.trim(), cwd: projectDir, topK })
      const data = JSON.parse(raw)
      if (data.error) setSearchErr(data.error)
      else setResults(data.results || [])
    } catch (e) {
      setSearchErr(String(e))
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="app">
      {/* 헤더 */}
      <header className="header">
        <span className="logo">Confulence</span>
        <div className="dir-row">
          <span className="dir-path" title={projectDir}>
            {projectDir || '프로젝트 폴더를 선택하세요'}
          </span>
          <button className="btn-sm" onClick={pickDir}>폴더 선택</button>
        </div>
      </header>

      {/* 탭 */}
      <nav className="tabs">
        {[
          { id: 'settings', label: '⚙  설정' },
          { id: 'run',      label: '▶  실행' },
          { id: 'search',   label: '🔍  검색' },
        ].map(t => (
          <button
            key={t.id}
            className={`tab-btn ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="main">

        {/* ── 설정 탭 ── */}
        {tab === 'settings' && (
          <div className="panel">
            <div className="fields">
              {ENV_FIELDS.map(f => (
                <div className="field-row" key={f.key}>
                  <label className="field-label">{f.label}</label>
                  <input
                    className="field-input"
                    type={f.type || 'text'}
                    placeholder={f.placeholder}
                    value={env[f.key] || ''}
                    onChange={e => setEnv({ ...env, [f.key]: e.target.value })}
                  />
                </div>
              ))}
            </div>
            <div className="save-row">
              <button className="btn-primary" onClick={saveEnv}>저장</button>
              {saveMsg && <span className="save-msg">{saveMsg}</span>}
            </div>
          </div>
        )}

        {/* ── 실행 탭 ── */}
        {tab === 'run' && (
          <div className="panel run-panel">
            <div className="run-btns">
              <button className="btn-run" disabled={running} onClick={() => runScript('backend/upload_content.py')}>
                📤  페이지 업로드
              </button>
              <button className="btn-run" disabled={running} onClick={() => runScript('backend/embed_pages.py')}>
                🧠  벡터 DB 임베딩
              </button>
              <button className="btn-clear" disabled={running} onClick={() => setOutput([])}>
                지우기
              </button>
            </div>
            <div className="terminal" ref={outputRef}>
              {output.length === 0
                ? <span className="t-placeholder">버튼을 눌러 스크립트를 실행하세요</span>
                : output.map((line, i) => (
                    <div key={i} className={line.startsWith('[ERR]') ? 'line-err' : 'line'}>{line}</div>
                  ))
              }
              {running && <span className="cursor">▌</span>}
            </div>
          </div>
        )}

        {/* ── 검색 탭 ── */}
        {tab === 'search' && (
          <div className="panel search-panel">
            <div className="search-bar">
              <input
                className="search-input"
                placeholder="검색어를 입력하세요  (예: VPN 설정, 강태민, 재택근무)"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && doSearch()}
              />
              <select
                className="topk-select"
                value={topK}
                onChange={e => setTopK(Number(e.target.value))}
              >
                {[3, 5, 10].map(n => <option key={n} value={n}>상위 {n}개</option>)}
              </select>
              <button className="btn-primary" onClick={doSearch} disabled={searching}>
                {searching ? '검색 중…' : '검색'}
              </button>
            </div>

            {searchErr && <div className="search-err">{searchErr}</div>}

            <div className="results">
              {results.length === 0 && !searching && !searchErr && (
                <div className="t-placeholder">검색 결과가 여기에 표시됩니다</div>
              )}
              {results.map((hit, i) => (
                <div className="result-card" key={i}>
                  <div className="result-head">
                    <span className="result-idx">{i + 1}</span>
                    <span className="result-title">{hit.metadata?.title}</span>
                    <span className="result-score">점수 {hit.score}</span>
                  </div>
                  <div className="result-crumb">{hit.metadata?.breadcrumb}</div>
                  {hit.metadata?.url && (
                    <a className="result-url" href={hit.metadata.url} target="_blank" rel="noreferrer">
                      {hit.metadata.url}
                    </a>
                  )}
                  <pre className="result-body">{hit.document}</pre>
                </div>
              ))}
            </div>
          </div>
        )}

      </main>
    </div>
  )
}
