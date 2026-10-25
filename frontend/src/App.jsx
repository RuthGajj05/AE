import { useEffect, useRef, useState } from 'react'
import { Dashboard } from './components/Dashboard.jsx'
import { MapView } from './components/MapView.jsx'
import { ErrorView, LoadingView } from './components/States.jsx'
import { DropOverlay } from './components/FileDrop.jsx'
import { IconUpload, Logo } from './components/Icons.jsx'
import { DATA_URL } from './config.js'
import { toDashboard } from './data/adapter.js'
import { useFileDrop } from './useFileDrop.js'
import savedReport from './data/capitol-hill-bakery-report.json'

const savedState = () => ({ status: 'ready', data: toDashboard(savedReport, { source: 'bundled' }) })

function describeError(err) {
  if (err instanceof SyntaxError) return "The data source didn't send valid JSON."
  if (err instanceof TypeError) return `Couldn't reach ${SOURCE_URL}. Is the backend running, and does it allow CORS?`
  return err?.message || 'Something went wrong loading the data.'
}

const viewFromHash = () => (window.location.hash === '#/map' ? 'map' : 'dashboard')

// ?business=<id> (linked from the crumbs Report tab) shows that business's latest advisor report from the backend.
const BUSINESS_ID = new URLSearchParams(window.location.search).get('business')
const SOURCE_URL = BUSINESS_ID ? `/api/business/${encodeURIComponent(BUSINESS_ID)}/report` : DATA_URL

/** The backend's report view says when there is nothing to show yet. */
function checkReportView(raw) {
  if (!BUSINESS_ID || raw?.report) return raw
  if (raw?.status === 'running') throw new Error('Your report is still being researched. Try again in a minute.')
  if (raw?.status === 'failed') throw new Error(raw.error || "The research didn't finish. Try again from the app.")
  throw new Error('There is no report for this business yet. Start one from the Report tab in the app.')
}

export default function App() {
  const [view, setView] = useState(viewFromHash)
  const [state, setState] = useState(() => (SOURCE_URL ? { status: 'loading' } : savedState()))
  const [attempt, setAttempt] = useState(0)
  const [toast, setToast] = useState(null)
  const fileInput = useRef(null)

  useEffect(() => {
    if (!SOURCE_URL) return
    const ctrl = new AbortController()
    fetch(SOURCE_URL, { signal: ctrl.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`The data source answered with an error (${res.status}).`)
        return res.json()
      })
      .then((raw) => setState({ status: 'ready', data: toDashboard(checkReportView(raw), { source: 'url' }) }))
      .catch((err) => {
        if (!ctrl.signal.aborted) setState({ status: 'error', message: describeError(err) })
      })
    return () => ctrl.abort()
  }, [attempt])

  useEffect(() => {
    const onHash = () => setView(viewFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(timer)
  }, [toast])

  const reload = () => {
    if (!SOURCE_URL) return setState(savedState())
    setState({ status: 'loading' })
    setAttempt((a) => a + 1)
  }

  async function loadFile(file) {
    if (!file) return
    try {
      const raw = JSON.parse(await file.text())
      setState({ status: 'ready', data: { ...toDashboard(raw, { source: 'file' }), fileName: file.name } })
      setToast({ kind: 'ok', text: `Loaded ${file.name}` })
    } catch {
      setToast({ kind: 'error', text: `${file.name} isn't valid JSON.` })
    }
  }

  const dragging = useFileDrop(loadFile)
  const data = state.status === 'ready' ? state.data : null

  return (
    <div className="app">
      <div className="backdrop" aria-hidden="true" />

      <header className="topbar">
        <div className="topbar-left">
          <div className="brand">
            <Logo />
            <span>LocalEdge</span>
          </div>
          <nav className="tabs" aria-label="Views">
            <a href="#/" className={view === 'dashboard' ? 'is-active' : undefined} aria-current={view === 'dashboard' ? 'page' : undefined}>
              Dashboard
            </a>
            <a href="#/map" className={view === 'map' ? 'is-active' : undefined} aria-current={view === 'map' ? 'page' : undefined}>
              Map
            </a>
          </nav>
        </div>
        <div className="topbar-actions">
          {data && <SourcePill data={data} onReset={reload} />}
          <button className="btn" onClick={() => fileInput.current?.click()}>
            <IconUpload />
            <span>Load JSON</span>
          </button>
          <input
            ref={fileInput}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(e) => {
              loadFile(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </div>
      </header>

      {data && view === 'map' ? (
        <main>
          <MapView data={data} />
        </main>
      ) : (
        <main className="page">
          {state.status === 'loading' && <LoadingView />}
          {state.status === 'error' && (
            <ErrorView message={state.message} onRetry={reload} onUseSaved={() => setState(savedState())} />
          )}
          {data && <Dashboard data={data} onLoadFile={() => fileInput.current?.click()} />}
        </main>
      )}

      {dragging && <DropOverlay />}
      {toast && (
        <div className={`toast toast-${toast.kind}`} role="status">
          {toast.text}
        </div>
      )}
    </div>
  )
}

function SourcePill({ data, onReset }) {
  if (data.source === 'file') {
    return (
      <span className="pill">
        <span className="pill-dot is-file" />
        <span className="pill-text">{data.fileName}</span>
        <button className="pill-x" onClick={onReset} aria-label="Stop using this file">
          ×
        </button>
      </span>
    )
  }
  const when = data.reportDate?.toLocaleDateString([], { month: 'short', day: 'numeric' })
  const label = data.source === 'url' ? 'Latest report' : 'Saved report'
  return (
    <span className="pill">
      <span className={`pill-dot${data.source === 'url' ? ' is-live' : ''}`} />
      <span className="pill-text">{when ? `${label} · ${when}` : label}</span>
    </span>
  )
}
