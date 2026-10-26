import { useEffect, useState } from 'react'
import { connectCsv, connectSquare, connectToast, disconnectSales, getSales } from './places.js'
import './sales.css'

const SOURCES = [
  { id: 'csv', label: 'CSV file' },
  { id: 'square', label: 'Square' },
  { id: 'toast', label: 'Toast' },
]

const day = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '')

function describe(status) {
  if (!status?.connected) return 'Not connected'
  const name = SOURCES.find((s) => s.id === status.source)?.label ?? status.source
  const detail = status.source === 'csv' && status.period ? `${status.label} · ${status.period}` : status.label
  return `${name}: ${detail}${status.environment === 'sandbox' ? ' (sandbox)' : ''}`
}

/**
 * Connect the spot's sales (optional): upload a CSV export, or connect Square or Toast. With sales, the report
 * compares your prices and best sellers with nearby spots and estimates dollar impact. Credentials go to the
 * crumbs backend, which checks and encrypts them; they never come back to the browser.
 *
 * `onDone(status)` runs after a successful connection (onboarding moves on); `refreshReport` asks the backend to
 * write a fresh report with the new sales.
 */
export function SalesConnect({ businessId, refreshReport = true, onDone }) {
  const [status, setStatus] = useState(null)
  const [source, setSource] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [file, setFile] = useState(null)
  const [square, setSquare] = useState({ accessToken: '', environment: 'production' })
  const [toast, setToast] = useState({ clientId: '', clientSecret: '', restaurantGuid: '' })

  useEffect(() => {
    let live = true
    getSales(businessId).then((r) => live && r.ok && setStatus(r.data))
    return () => {
      live = false
    }
  }, [businessId])

  async function connect(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const opts = { refreshReport }
    const r =
      source === 'csv'
        ? await connectCsv(businessId, file, opts)
        : source === 'square'
          ? await connectSquare(businessId, square, opts)
          : await connectToast(businessId, toast, opts)
    setBusy(false)
    if (!r.ok) return setError(r.error)
    setStatus(r.data)
    setSource(null)
    setSquare((s) => ({ ...s, accessToken: '' }))
    setToast({ clientId: '', clientSecret: '', restaurantGuid: '' })
    setNotice(r.data.reportStarted ? 'Connected. Your report is being rewritten with your sales (about a minute).' : 'Connected.')
    onDone?.(r.data)
  }

  async function disconnect() {
    setBusy(true)
    const r = await disconnectSales(businessId)
    setBusy(false)
    if (r.ok) {
      setStatus(r.data)
      setNotice('Disconnected. Future reports won’t use sales data.')
    } else setError(r.error)
  }

  return (
    <div className="sales">
      <p className="sales-status">
        <span className={status?.connected ? 'sales-dot is-on' : 'sales-dot'} aria-hidden="true" />
        {status ? describe(status) : 'Checking…'}
        {status?.connectedAt && <span className="sales-muted"> · since {day(status.connectedAt)}</span>}
      </p>
      {notice && (
        <p className="sales-notice" role="status">
          {notice}
        </p>
      )}

      <div className="sales-choices" role="group" aria-label="Sales source">
        {SOURCES.map((s) => (
          <button
            key={s.id}
            type="button"
            className={source === s.id ? 'is-on' : undefined}
            aria-pressed={source === s.id}
            onClick={() => {
              setSource(source === s.id ? null : s.id)
              setError(null)
              setNotice(null)
            }}
          >
            {status?.source === s.id ? `Replace ${s.label}` : s.label}
          </button>
        ))}
      </div>

      {source && (
        <form className="sales-form" onSubmit={connect}>
          {source === 'csv' && (
            <>
              <label className="onb-field">
                <span>Sales export (CSV)</span>
                <input id="sales-csv" type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
              </label>
              <p className="sales-help">
                Columns: Date, Time, Item, Qty, Gross Sales (Square: Reports → Item sales → Export). About 8 weeks works best.
              </p>
            </>
          )}
          {source === 'square' && (
            <>
              <label className="onb-field">
                <span>Square access token</span>
                <input
                  id="sales-square-token"
                  type="password"
                  autoComplete="off"
                  value={square.accessToken}
                  onChange={(e) => setSquare((s) => ({ ...s, accessToken: e.target.value }))}
                  required
                />
              </label>
              <label className="onb-field">
                <span>Environment</span>
                <select id="sales-square-env" value={square.environment} onChange={(e) => setSquare((s) => ({ ...s, environment: e.target.value }))}>
                  <option value="production">Production (real sales)</option>
                  <option value="sandbox">Sandbox (test data)</option>
                </select>
              </label>
              <p className="sales-help">From developer.squareup.com → your app → Credentials. We only read orders.</p>
            </>
          )}
          {source === 'toast' && (
            <>
              {[
                ['clientId', 'Client ID', 'text'],
                ['clientSecret', 'Client secret', 'password'],
                ['restaurantGuid', 'Restaurant GUID', 'text'],
              ].map(([key, label, type]) => (
                <label key={key} className="onb-field">
                  <span>{label}</span>
                  <input
                    id={`sales-toast-${key}`}
                    type={type}
                    autoComplete="off"
                    value={toast[key]}
                    onChange={(e) => setToast((t) => ({ ...t, [key]: e.target.value }))}
                    required
                  />
                </label>
              ))}
              <p className="sales-help">From Toast Web → Integrations → Toast API access → Manage credentials (read access to orders).</p>
            </>
          )}
          {error && (
            <p className="onb-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="onb-primary" disabled={busy}>
            {busy ? 'Checking…' : source === 'csv' ? 'Upload' : 'Connect'}
          </button>
        </form>
      )}

      {!source && error && (
        <p className="onb-error" role="alert">
          {error}
        </p>
      )}
      {status?.connected && !source && (
        <button type="button" className="sales-disconnect" onClick={disconnect} disabled={busy}>
          Disconnect
        </button>
      )}
    </div>
  )
}
