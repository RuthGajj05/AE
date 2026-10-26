import { useCallback, useEffect, useRef, useState } from 'react'
import { getAdvisorReport, refreshAdvisorReport } from './places.js'
import './report.css'

// While the backend researches (about a minute), ask again every few seconds, for at most a few minutes.
const POLL_MS = 5000
const POLL_LIMIT_MS = 4 * 60 * 1000

const money = (usd) => (usd ? `~$${Math.round(usd).toLocaleString()}/mo` : null)
const day = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '')

/**
 * The owner's tailored report from Ruth's advisor (via the backend): what to do next, with the evidence and math
 * behind each tip, product gaps, and the competitors it was based on. Without a registered spot (or backend), it
 * shows the saved example report, labeled as a sample.
 */
export function ReportView({ businessId }) {
  const [state, setState] = useState({ loading: true, view: null, offline: false })
  const pollStart = useRef(null)

  const load = useCallback(async () => {
    const view = await getAdvisorReport(businessId ?? 'demo', { demo: !businessId })
    setState({ loading: false, view, offline: view === null })
    return view
  }, [businessId])

  useEffect(() => {
    let live = true
    let timer = null
    pollStart.current = Date.now()
    const tick = async () => {
      const view = await load()
      if (live && view?.status === 'running' && Date.now() - pollStart.current < POLL_LIMIT_MS) {
        timer = setTimeout(tick, POLL_MS)
      }
    }
    tick()
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [load, state.refreshes])

  async function refresh() {
    setState((s) => ({ ...s, view: s.view && { ...s.view, status: 'running', error: null } }))
    await refreshAdvisorReport(businessId)
    setState((s) => ({ ...s, refreshes: (s.refreshes ?? 0) + 1 }))
  }

  const { loading, view, offline } = state
  if (loading) return <p className="rep-note">Loading your report…</p>
  if (offline) return <p className="rep-note">Reports need the crumbs backend. Start it and open this tab again.</p>

  const sample = !businessId || view.demo
  const running = view.status === 'running'
  const s = view.summary

  return (
    <div className="rep">
      <section className="rep-head">
        <p className="rep-eyebrow">{sample ? 'Example report' : 'Your report'}</p>
        <h1>{s?.business ?? 'Your spot'}</h1>
        <p className="rep-sub">
          {s?.location}
          {s?.date && ` · ${day(view.createdAt ?? s.date)}`}
          {s && !s.usedSales && <span className="rep-tag">no sales data</span>}
        </p>
        {running && <p className="rep-status is-running">Researching nearby spots… about a minute.</p>}
        {view.status === 'failed' && <p className="rep-status is-failed">{view.error}</p>}
        {view.status === 'none' && <p className="rep-status">No report yet.</p>}
        {sample && <p className="rep-status">Set up your spot to get your own report.</p>}
        {!sample && (
          <div className="rep-actions">
            <button className="rep-btn" onClick={refresh} disabled={running}>
              {running ? 'Researching…' : view.status === 'none' ? 'Write my report' : 'Refresh report'}
            </button>
            {s && (
              <a className="rep-link" href={`/localedge.html?business=${encodeURIComponent(businessId)}`}>
                Full competitor report
              </a>
            )}
          </div>
        )}
      </section>

      {s && (
        <>
          {s.snapshot && <p className="rep-snapshot">{s.snapshot}</p>}

          <h2 className="biz-label">What to do next</h2>
          <ol className="rep-recs">
            {s.recommendations.map((r, i) => (
              <li key={i} className="rep-rec">
                <div className="rep-rec-top">
                  <span className="rep-cat">{r.category}</span>
                  {money(r.monthlyImpactUsd) && <span className="rep-impact">{money(r.monthlyImpactUsd)}</span>}
                  <span className={`rep-conf is-${r.confidence}`}>{r.confidence} confidence</span>
                </div>
                <h3>{r.title}</h3>
                <p>{r.action}</p>
                <details>
                  <summary>Why</summary>
                  {r.evidenceYours && r.evidenceYours !== 'none' && (
                    <p>
                      <b>Your data:</b> {r.evidenceYours}
                    </p>
                  )}
                  {r.evidenceMarket && r.evidenceMarket !== 'none' && (
                    <p>
                      <b>Nearby:</b> {r.evidenceMarket}
                    </p>
                  )}
                  {r.impactMath && (
                    <p className="rep-math">
                      <b>The math:</b> {r.impactMath}
                    </p>
                  )}
                </details>
              </li>
            ))}
          </ol>

          {s.productGaps.length > 0 && (
            <>
              <h2 className="biz-label">Sold nearby, not by you</h2>
              <ul className="rep-gaps">
                {s.productGaps.map((g) => (
                  <li key={g.product}>
                    <b>{g.product}</b> at {g.competitorCount} spots ({g.competitors.slice(0, 3).join(', ')})
                    {g.needsConfirmation && <span className="rep-muted"> · check whether you carry it</span>}
                  </li>
                ))}
              </ul>
            </>
          )}

          <h2 className="biz-label">Spots we compared you with</h2>
          <ul className="rep-comps">
            {s.competitors.map((c) => (
              <li key={c.name}>
                <span className="rep-comp-name">{c.name}</span>
                <span className="rep-muted">
                  {c.rating != null ? `★ ${c.rating}${c.reviewCount ? ` (${c.reviewCount})` : ''}` : 'no rating found'}
                  {c.pricePoints[0] && ` · ${c.pricePoints[0]}`}
                </span>
              </li>
            ))}
          </ul>

          {s.caveats.length > 0 && (
            <details className="rep-caveats">
              <summary>What we couldn't verify ({s.caveats.length})</summary>
              <ul>
                {s.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  )
}
