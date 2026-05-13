import { useState, useEffect, useRef } from 'react'
import { invoke } from '@tauri-apps/api/tauri'
import { listen } from '@tauri-apps/api/event'
import { open } from '@tauri-apps/api/dialog'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const ENV_FIELDS = [
  { key: 'CONFLUENCE_BASE_URL',   label: 'Confluence URL',   placeholder: 'https://your-domain.atlassian.net' },
  { key: 'CONFLUENCE_EMAIL',      label: '이메일',            placeholder: 'your@email.com' },
  { key: 'CONFLUENCE_API_TOKEN',  label: 'API 토큰',          placeholder: 'your_api_token', type: 'password' },
  { key: 'CONFLUENCE_SPACE_KEY',  label: 'Space Key',         placeholder: 'NAW' },
  { key: 'ROOT_PAGE_ID',          label: '루트 페이지 ID',     placeholder: '622768' },
  { key: 'CHUNK_SIZE',            label: '청크 크기 (글자)',   placeholder: '500' },
  { key: 'CHUNK_OVERLAP',         label: '청크 오버랩 (글자)', placeholder: '50' },
  { key: 'RERANK_FETCH_K',        label: '리랭킹 후보 수',     placeholder: '20' },
  { key: 'RERANK_THRESHOLD',      label: '리랭킹 임계값',      placeholder: '-1.0' },
]

export default function App() {
  const [tab, setTab]               = useState('settings')
  const [projectDir, setProjectDir] = useState(() => localStorage.getItem('projectDir') || '')
  const [env, setEnv]               = useState({})
  const [dirty, setDirty]           = useState(false)
  const [saveMsg, setSaveMsg]       = useState('')
  const [running, setRunning]       = useState(false)
  const [runStatus, setRunStatus]   = useState('idle') // 'idle' | 'running' | 'done' | 'error'
  const [output, setOutput]         = useState([])
  const [query, setQuery]           = useState('')
  const [topK, setTopK]             = useState(5)
  const [searching, setSearching]   = useState(false)
  const [results, setResults]       = useState([])
  const [searchErr, setSearchErr]   = useState('')
  const [viewMode, setViewMode]     = useState('chunk') // 'chunk' | 'page'
  const [alpha, setAlpha]           = useState(0.4)
  const [collections, setCollections] = useState([])
  const [selectedCol, setSelectedCol] = useState('')
  const [deleteCol, setDeleteCol]     = useState('')
  const [deleting, setDeleting]       = useState(false)
  const [colErr, setColErr]           = useState('')
  const outputRef = useRef(null)

  // ── 챗봇 ──
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput]       = useState('')
  const [chatting, setChatting]         = useState(false)
  const [chatCol, setChatCol]           = useState('')
  const [chatTopK, setChatTopK]         = useState(5)
  const [chatAlpha, setChatAlpha]       = useState(0.4)
  const chatEndRef = useRef(null)

  useEffect(() => {
    if (!projectDir) {
      invoke('get_exe_dir').then(dir => {
        setProjectDir(dir)
        localStorage.setItem('projectDir', dir)
      }).catch(() => {})
    }
  }, [])

  useEffect(() => {
    if (projectDir) loadEnv()
  }, [projectDir])

  useEffect(() => {
    if (outputRef.current)
      outputRef.current.scrollTop = outputRef.current.scrollHeight
  }, [output])

  useEffect(() => {
    if ((tab === 'search' || tab === 'run' || tab === 'chat') && projectDir) loadCollections()
  }, [tab, projectDir])

  useEffect(() => {
    if (chatEndRef.current) chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  async function loadCollections() {
    setColErr('')
    try {
      const raw  = await invoke('list_collections', { cwd: projectDir })
      if (!raw || !raw.trim()) { setColErr('응답 없음 (앱 재시작 필요)'); return }
      const data = JSON.parse(raw)
      if (data.error) { setColErr(data.error); return }
      const list = data.collections || []
      setCollections(list)
      if (list.length > 0) {
        if (!list.includes(selectedCol)) setSelectedCol(list[0])
        if (!list.includes(deleteCol))   setDeleteCol(list[0])
      }
    } catch (e) {
      setColErr(String(e))
    }
  }

  async function doDelete() {
    if (!deleteCol) return
    const parts   = deleteCol.split('_')
    const overlap = parts[parts.length - 1]
    const chunk   = parts[parts.length - 2]
    if (!window.confirm(`"청크 ${chunk} / 오버랩 ${overlap}" 컬렉션을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return
    setDeleting(true)
    try {
      const raw  = await invoke('delete_collection', { cwd: projectDir, collection: deleteCol })
      const data = JSON.parse(raw)
      if (data.ok) await loadCollections()
      else alert(`삭제 실패: ${data.error}`)
    } catch (e) {
      alert(String(e))
    } finally {
      setDeleting(false)
    }
  }

  async function sendChat() {
    if (!projectDir) return alert('프로젝트 폴더를 먼저 선택하세요')
    if (!chatInput.trim() || chatting) return

    const question = chatInput.trim()
    setChatInput('')
    setChatting(true)
    setChatMessages(prev => [
      ...prev,
      { role: 'user', content: question },
      { role: 'assistant', content: '', sources: [], streaming: true, status: '쿼리 정제 중...' },
    ])

    const unlisten = await listen('chat_output', (event) => {
      const line = event.payload
      if (line.startsWith('__ERR__')) return

      try {
        const data = JSON.parse(line)
        if (data.status !== undefined) {
          setChatMessages(prev => {
            const msgs = [...prev]
            msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], status: data.status }
            return msgs
          })
        } else if (data.t !== undefined) {
          setChatMessages(prev => {
            const msgs = [...prev]
            msgs[msgs.length - 1] = {
              ...msgs[msgs.length - 1],
              status: '',
              content: msgs[msgs.length - 1].content + data.t,
            }
            return msgs
          })
        } else if (data.sources) {
          setChatMessages(prev => {
            const msgs = [...prev]
            msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], sources: data.sources }
            return msgs
          })
        } else if (data.done) {
          setChatMessages(prev => {
            const msgs = [...prev]
            msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], streaming: false }
            return msgs
          })
          setChatting(false)
          unlisten()
        } else if (data.error) {
          setChatMessages(prev => {
            const msgs = [...prev]
            msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: `오류: ${data.error}`, streaming: false }
            return msgs
          })
          setChatting(false)
          unlisten()
        }
      } catch (_) {}
    })

    try {
      await invoke('run_chat', {
        question,
        cwd:        projectDir,
        collection: chatCol || collections[0] || '',
        topK:       chatTopK,
        alpha:      chatAlpha,
      })
    } catch (e) {
      setChatMessages(prev => {
        const msgs = [...prev]
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: `오류: ${e}`, streaming: false }
        return msgs
      })
      setChatting(false)
      unlisten()
    }
  }

  async function pickDir() {
    const dir = await open({ directory: true, title: '프로젝트 폴더 선택' })
    if (!dir) return
    setProjectDir(dir)
    localStorage.setItem('projectDir', dir)
  }

  async function loadEnv() {
    try {
      const data = await invoke('read_env', { path: `${projectDir}\\.env` })
      setEnv(data)
      setDirty(false)
      setSaveMsg('')
    } catch (e) {
      console.error(e)
    }
  }

  async function saveEnv() {
    if (!projectDir) {
      setSaveMsg('✗ 프로젝트 폴더를 먼저 선택하세요')
      return
    }
    try {
      await invoke('save_env', { path: `${projectDir}\\.env`, values: env })
      setDirty(false)
      setSaveMsg('✓ 저장됨')
    } catch (e) {
      setSaveMsg(`✗ ${e}`)
    }
  }

  async function runScript(script) {
    if (!projectDir) return alert('프로젝트 폴더를 먼저 선택하세요')
    if (running) return
    setRunning(true)
    setRunStatus('running')
    setOutput([`▶  python ${script}`])

    const unlisten = await listen('script_output', (event) => {
      if (event.payload === '__DONE__') {
        setRunning(false)
        setRunStatus('done')
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
      setRunStatus('error')
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
      const raw  = await invoke('run_search', { query: query.trim(), cwd: projectDir, topK, collection: selectedCol, alpha })
      const data = JSON.parse(raw)
      if (data.error) setSearchErr(data.error)
      else setResults(data.results || [])
    } catch (e) {
      setSearchErr(String(e))
    } finally {
      setSearching(false)
    }
  }

  function aggregateByPage(chunks) {
    const pageMap = {}
    chunks.forEach(hit => {
      const id = hit.metadata?.page_id || hit.metadata?.title
      if (!pageMap[id]) {
        pageMap[id] = { metadata: hit.metadata, chunkCount: 1, chunks: [hit], best: hit }
      } else {
        pageMap[id].chunkCount++
        pageMap[id].chunks.push(hit)
        if (hit.score > pageMap[id].best.score) pageMap[id].best = hit
      }
    })
    return Object.values(pageMap)
      .map(page => {
        const sorted = [...page.chunks].sort(
          (a, b) => Number(a.metadata?.chunk_index ?? 0) - Number(b.metadata?.chunk_index ?? 0)
        )
        return {
          metadata:     page.metadata,
          chunkCount:   page.chunkCount,
          document:     sorted.map(c => c.document).join('\n\n'),
          score:        page.best.score,
          vector_score: page.best.vector_score,
          bm25_score:   page.best.bm25_score,
        }
      })
      .sort((a, b) => b.score - a.score)
  }

  const displayResults = viewMode === 'page' ? aggregateByPage(results) : results

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
          { id: 'chat',     label: '💬  챗봇' },
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
                    onChange={e => { setEnv({ ...env, [f.key]: e.target.value }); setDirty(true); setSaveMsg('') }}
                  />
                </div>
              ))}
            </div>
            {projectDir && (
              <div className="info-box">
                <div className="info-row">
                  <span className="info-label">Vector DB</span>
                  <span className="info-value">{projectDir}\vector_db</span>
                </div>
                <div className="info-row">
                  <span className="info-label">컬렉션</span>
                  <span className="info-value">
                    {`${env.VECTOR_DB_COLLECTION || 'confluence'}_${env.CHUNK_SIZE || '500'}_${env.CHUNK_OVERLAP || '50'}`}
                  </span>
                </div>
              </div>
            )}
            <div className="save-row">
              <button className={`btn-primary${dirty ? ' btn-dirty' : ''}`} onClick={saveEnv}>저장</button>
              {dirty && !saveMsg && <span className="save-msg unsaved">● 저장되지 않은 변경사항</span>}
              {saveMsg && <span className={`save-msg${saveMsg.startsWith('✗') ? ' save-err' : ''}`}>{saveMsg}</span>}
            </div>
          </div>
        )}

        {/* ── 실행 탭 ── */}
        {tab === 'run' && (
          <div className="panel run-panel">
            <div className="run-btns">
              <button className="btn-run" disabled={running} onClick={() => runScript('backend/upload_content.py')}>
                {running ? '⏳  실행 중...' : '📤  페이지 업로드'}
              </button>
              <button className="btn-run" disabled={running} onClick={() => runScript('backend/embed_pages.py')}>
                {running ? '⏳  실행 중...' : '🧠  벡터 DB 임베딩'}
              </button>
              <button className="btn-clear" disabled={running} onClick={() => { setOutput([]); setRunStatus('idle') }}>
                지우기
              </button>
            </div>
            {colErr && <div className="search-err" style={{fontSize:'12px'}}>컬렉션 로드 실패: {colErr}</div>}
            <div className="delete-bar">
              <select
                className="col-select"
                value={deleteCol}
                onChange={e => setDeleteCol(e.target.value)}
                disabled={collections.length === 0 || running || deleting}
              >
                {collections.length === 0
                  ? <option>임베딩된 컬렉션 없음</option>
                  : collections.map(c => {
                      const parts = c.split('_')
                      const overlap = parts[parts.length - 1]
                      const chunk   = parts[parts.length - 2]
                      return <option key={c} value={c}>청크 {chunk} / 오버랩 {overlap}</option>
                    })
                }
              </select>
              <button
                className="btn-delete"
                disabled={collections.length === 0 || running || deleting}
                onClick={doDelete}
              >
                {deleting ? '삭제 중...' : '컬렉션 삭제'}
              </button>
              <button className="btn-sm" onClick={loadCollections} disabled={running || deleting}>↺</button>
            </div>

            {runStatus !== 'idle' && (
              <div className={`run-status run-status-${runStatus}`}>
                {runStatus === 'running' && <><span className="status-dot blink">●</span> 실행 중...</>}
                {runStatus === 'done'    && <><span className="status-dot">●</span> 완료</>}
                {runStatus === 'error'   && <><span className="status-dot">●</span> 오류 발생</>}
              </div>
            )}
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
            {colErr && <div className="search-err">컬렉션 로드 실패: {colErr}</div>}
            <div className="col-bar">
              <select
                className="col-select"
                value={selectedCol}
                onChange={e => setSelectedCol(e.target.value)}
                disabled={collections.length === 0}
              >
                {collections.length === 0
                  ? <option>임베딩된 컬렉션 없음</option>
                  : collections.map(c => {
                      const parts = c.split('_')
                      const overlap = parts[parts.length - 1]
                      const chunk   = parts[parts.length - 2]
                      return <option key={c} value={c}>청크 {chunk} / 오버랩 {overlap}</option>
                    })
                }
              </select>
              <button className="btn-sm" onClick={loadCollections}>↺</button>
            </div>
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
              <div className="alpha-control">
                <span className="alpha-label">BM25</span>
                <input
                  type="range" min="0" max="1" step="0.05"
                  value={alpha}
                  onChange={e => setAlpha(Number(e.target.value))}
                  className="alpha-slider"
                />
                <span className="alpha-label">벡터</span>
                <input
                  type="number" min="0" max="1" step="0.05"
                  value={alpha}
                  onChange={e => setAlpha(Math.min(1, Math.max(0, Number(e.target.value))))}
                  className="alpha-number"
                />
              </div>
              <button className="btn-primary" onClick={doSearch} disabled={searching}>
                {searching ? '검색 중…' : '검색'}
              </button>
            </div>

            {results.length > 0 && (
              <div className="view-toggle">
                <button className={`toggle-btn${viewMode === 'chunk' ? ' active' : ''}`} onClick={() => setViewMode('chunk')}>
                  청크
                </button>
                <button className={`toggle-btn${viewMode === 'page' ? ' active' : ''}`} onClick={() => setViewMode('page')}>
                  페이지
                </button>
                <span className="toggle-count">
                  {viewMode === 'chunk'
                    ? `${results.length}개 청크`
                    : `${displayResults.length}개 페이지`}
                </span>
              </div>
            )}

            {searchErr && <div className="search-err">{searchErr}</div>}

            <div className="results">
              {results.length === 0 && !searching && !searchErr && (
                <div className="t-placeholder">검색 결과가 여기에 표시됩니다</div>
              )}
              {displayResults.map((hit, i) => (
                <div className="result-card" key={i}>
                  <div className="result-head">
                    <span className="result-idx">{i + 1}</span>
                    <span className="result-title">{hit.metadata?.title}</span>
                    <div className="result-badges">
                      {viewMode === 'page' && hit.chunkCount > 1 && (
                        <span className="badge-chunk">{hit.chunkCount}개 청크</span>
                      )}
                      {hit.vector_score != null && (
                        <span className="score-badge score-vec"
                          title={"벡터 유사도 (코사인 유사도)\n범위: 0 ~ 1\n1에 가까울수록 쿼리와 의미적으로 유사"}>
                          벡터 {hit.vector_score}
                        </span>
                      )}
                      {hit.bm25_score != null && (
                        <span className="score-badge score-bm25"
                          title={"BM25 키워드 매칭 점수\n범위: 0 이상 (상한 없음)\n고유명사·코드·이름 검색에 강함"}>
                          BM25 {hit.bm25_score}
                        </span>
                      )}
                      {alpha > 0 && alpha < 1 && (
                        <span className="score-badge score-rrf"
                          title={"RRF (Reciprocal Rank Fusion) 통합 점수\n벡터 순위와 BM25 순위를 합산한 최종 점수"}>
                          RRF {hit.score}
                        </span>
                      )}
                    </div>
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

        {/* ── 챗봇 탭 ── */}
        {tab === 'chat' && (
          <div className="panel chat-panel">
            {/* 상단 옵션 바 */}
            <div className="chat-options">
              <select
                className="col-select"
                value={chatCol || collections[0] || ''}
                onChange={e => setChatCol(e.target.value)}
                disabled={collections.length === 0}
              >
                {collections.length === 0
                  ? <option>임베딩된 컬렉션 없음</option>
                  : collections.map(c => {
                      const parts = c.split('_')
                      const overlap = parts[parts.length - 1]
                      const chunk   = parts[parts.length - 2]
                      return <option key={c} value={c}>청크 {chunk} / 오버랩 {overlap}</option>
                    })
                }
              </select>
              <div className="alpha-control">
                <span className="alpha-label">BM25</span>
                <input type="range" min="0" max="1" step="0.05"
                  value={chatAlpha} onChange={e => setChatAlpha(Number(e.target.value))}
                  className="alpha-slider" />
                <span className="alpha-label">벡터</span>
                <input type="number" min="0" max="1" step="0.05"
                  value={chatAlpha}
                  onChange={e => setChatAlpha(Math.min(1, Math.max(0, Number(e.target.value))))}
                  className="alpha-number" />
              </div>
              <select className="topk-select" value={chatTopK} onChange={e => setChatTopK(Number(e.target.value))}>
                {[3, 5, 10].map(n => <option key={n} value={n}>참고 {n}개</option>)}
              </select>
              <button className="btn-sm" onClick={() => setChatMessages([])}>지우기</button>
            </div>

            {/* 메시지 영역 */}
            <div className="chat-messages">
              {chatMessages.length === 0 && (
                <div className="chat-placeholder">질문을 입력하면 Confluence 문서 기반으로 답변합니다</div>
              )}
              {chatMessages.map((msg, i) => (
                <div key={i} className={`chat-msg chat-msg-${msg.role}`}>
                  <div className="chat-bubble">
                    {msg.role === 'assistant' && msg.streaming && msg.status && !msg.content && (
                      <span className="chat-status">{msg.status}</span>
                    )}
                    {msg.role === 'assistant'
                      ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      : msg.content
                    }
                    {msg.streaming && msg.content && <span className="cursor">▌</span>}
                  </div>
                  {msg.role === 'assistant' && !msg.streaming && msg.sources?.length > 0 && (
                    <div className="chat-sources">
                      <span className="chat-sources-label">참고 문서</span>
                      {msg.sources.map((s, j) => (
                        <a key={j} className="chat-source-item" href={s.url} target="_blank" rel="noreferrer"
                          title={s.breadcrumb}>
                          {s.title}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            {/* 입력 바 */}
            <div className="chat-input-bar">
              <input
                className="chat-input"
                placeholder="Confluence 문서에 대해 질문하세요..."
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendChat()}
                disabled={chatting}
              />
              <button className="btn-primary" onClick={sendChat} disabled={chatting || !chatInput.trim()}>
                {chatting ? '생성 중…' : '전송'}
              </button>
            </div>
          </div>
        )}

      </main>
    </div>
  )
}
