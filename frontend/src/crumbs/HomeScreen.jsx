import { useEffect, useState } from 'react'
import { isBusiness, useAccount } from './account.js'
import './home.css'
import { IconLock } from './icons.jsx'
import { formatMetric, gapScore, isScore, isWait, mentionText, metricValue, scaleMax } from './metrics.js'
import { getBusinessReport } from './places.js'
import { ReportView } from './ReportView.jsx'

const VIEWS = [
  { id: 'report', label: 'Report' },
  { id: 'insights', label: 'Insights' },
  { id: 'rivals', label: 'Rivals' },
]

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

/** Home: the business dashboard. Consumers see it locked, with a way into business onboarding. */
export function HomeScreen() {
  const { account, startOnboarding } = useAccount()
  return isBusiness(account) ? (
    <BusinessHome name={account.business.name} businessId={account.business.id} cuisine={account.business.cuisine} />
  ) : (
    <LockedHome onStart={startOnboarding} />
  )
}

function Switch({ view, onView, disabled = false }) {
  return (
    <div className="biz-switch" role="tablist" aria-label="Business views">
      {VIEWS.map((v) => (
        <button
          key={v.id}
          role="tab"
          aria-selected={view === v.id}
          className={view === v.id ? 'is-on' : undefined}
          onClick={() => onView?.(v.id)}
          disabled={disabled}
        >
          {v.label}
        </button>
      ))}
    </div>
  )
}

function BusinessHome({ name, businessId, cuisine }) {
  const [view, setView] = useState('report')
  const [report, setReport] = useState(null)

  // Mounted fresh on every visit to the tab, so new Go-here picks show up.
  useEffect(() => {
    let live = true
    getBusinessReport()
      .then((r) => live && setReport(r))
      .catch((err) => console.warn('[crumbs] Business report failed.', err))
    return () => {
      live = false
    }
  }, [])

  return (
    <div className="biz">
      <Switch view={view} onView={setView} />
      {view === 'report' && <ReportView businessId={businessId} />}
      {view !== 'report' && !cuisine && (
        <p className="rep-note">
          Insights and Rivals compare spots that crumbs members rate by food type (sushi, ramen, pizza, tacos, steak).
          They aren't available for your kind of business yet; your Report covers your competitors.
        </p>
      )}
      {cuisine && report && view === 'insights' && <Insights report={report} name={name} />}
      {cuisine && report && view === 'rivals' && <Rivals report={report} name={name} />}
    </div>
  )
}

// ---------- Insights ----------

const average = (values) => values.reduce((sum, v) => sum + v, 0) / values.length

/**
 * The three rings, 0–100. Reputation = your average review score. Momentum = share of compared picks you won.
 * Edge = share of attributes where you beat the area average.
 */
function ringScores(report) {
  const rows = report.breakdown.filter((r) => r.you != null && r.area != null)
  const scores = rows.filter((r) => isScore(r.attr)).map((r) => r.you)
  const picks = report.picksWon + report.picksLost
  return [
    { id: 'reputation', label: 'Reputation', value: scores.length ? Math.round(average(scores)) : 0 },
    { id: 'momentum', label: 'Momentum', value: picks ? Math.round((report.picksWon / picks) * 100) : 0 },
    {
      id: 'edge',
      label: 'Edge',
      value: rows.length ? Math.round((rows.filter((r) => gapScore(r.attr, r.you, r.area) < 0).length / rows.length) * 100) : 0,
    },
  ]
}

function Ring({ label, value }) {
  const r = 38
  const c = 2 * Math.PI * r
  const shown = value === null ? 0 : value
  return (
    <div className="ring">
      <svg viewBox="0 0 92 92" width="92" height="92" aria-hidden="true">
        <circle cx="46" cy="46" r={r} className="ring-track" />
        {/* A zero-length round-capped stroke still draws a dot, so skip it. */}
        {shown > 0 && (
          <circle cx="46" cy="46" r={r} className="ring-fill" strokeDasharray={`${(shown / 100) * c} ${c}`} transform="rotate(-90 46 46)" />
        )}
      </svg>
      <span className="ring-value">{value === null ? '' : value}</span>
      <span className="ring-label">{label}</span>
    </div>
  )
}

function Insights({ report, name }) {
  const { you, breakdown, drag, rivals, biggestGapId } = report
  const gap = rivals.find((r) => r.spot.id === biggestGapId)

  return (
    <>
      <section className="whoop" aria-label="Your scores">
        <p className="whoop-eyebrow">{name}</p>
        <h1>Insights</h1>
        <p className="whoop-sub">
          {report.cuisine.label} · {report.area} · {report.period}
        </p>
        <div className="rings">
          {ringScores(report).map((ring) => (
            <Ring key={ring.id} label={ring.label} value={ring.value} />
          ))}
        </div>
        <p className="rings-note">Reputation = avg review score · Momentum = picks you won · Edge = areas you beat nearby</p>
      </section>

      <h2 className="biz-label">Breakdown</h2>
      <ul className="breakdown">
        {breakdown.map((row) => (
          <li key={row.attr.id}>
            <div className="breakdown-top">
              <span className="breakdown-name">{row.attr.label}</span>
              <span className="breakdown-value">
                {row.attr.id === 'ambiance'
                  ? `${formatMetric(row.attr, row.you)} positive · ${mentionText(you.ambianceMentionRate)}`
                  : `${formatMetric(row.attr, row.you)} · area ${formatMetric(row.attr, row.area)}`}
              </span>
            </div>
            {row.you != null && row.area != null && <GapBar attr={row.attr} you={row.you} other={row.area} otherLabel="Area" compact />}
            {isWait(row.attr) && <p className="breakdown-note">Shorter is better</p>}
          </li>
        ))}
      </ul>

      <div className="insight-cards">
        {drag && (
          <section className="drag-card">
            <span className="biz-label">Biggest drag</span>
            <h2>{drag.attr.label}</h2>
            <p>
              {isWait(drag.attr)
                ? `${drag.you} min avg, ${drag.you - drag.area} min longer than spots nearby.`
                : `${formatMetric(drag.attr, drag.you)}, ${drag.area - drag.you} pts below spots nearby.`}
            </p>
          </section>
        )}
        {gap?.reason && (
          <section className="gap-card">
            <span className="biz-label">The gap</span>
            <h2>{gap.spot.name}</h2>
            <p>
              Beats you on <b>{gap.reason.attr.label.toLowerCase()}</b> · {gap.reason.text}
            </p>
            <GapBar attr={gap.reason.attr} you={gap.reason.you} other={gap.reason.rival} otherLabel={gap.spot.name} />
          </section>
        )}
      </div>
    </>
  )
}

// ---------- Rivals ----------

function Rivals({ report, name }) {
  const { you, rivals, wins, biggestGapId } = report
  return (
    <>
      <header className="biz-head">
        <h1>Rivals</h1>
        <p>
          {name} · {report.cuisine.label} · {report.area} · {report.period}
        </p>
      </header>

      <section className="lost-card">
        <div className="lost-nums">
          <span className="lost-big">{plural(report.picksLost, 'pick')} lost</span>
          <span className="lost-divider" aria-hidden="true" />
          <span className="lost-won">{plural(report.picksWon, 'pick')} won</span>
        </div>
        <p>crumbs users nearby who compared you, then chose a spot.</p>
        {report.localPicks > 0 && <p className="lost-local">Includes {plural(report.localPicks, 'pick')} made on this device.</p>}
      </section>

      <h2 className="biz-label">Why they chose someone else</h2>
      <ol className="rival-list">
        {rivals.map(({ spot, picksWon, reason }) => {
          const isBiggest = spot.id === biggestGapId
          return (
            <li key={spot.id} className={`rival-card${isBiggest ? ' is-biggest' : ''}`}>
              <div className="rival-top">
                <p>
                  <b>{spot.name}</b> won {plural(picksWon, 'pick')}
                  {reason && (
                    <>
                      , likely because of your <b>{reason.attr.label.toLowerCase()}</b>
                    </>
                  )}
                </p>
                {reason && <span className={`gap-tag${isBiggest ? ' is-biggest' : ''}`}>{reason.text}</span>}
              </div>
              {reason && <GapBar attr={reason.attr} you={reason.you} other={reason.rival} otherLabel={spot.name} />}
            </li>
          )
        })}
      </ol>

      {wins.length > 0 && (
        <p className="wins-row">
          <b>Where you win:</b> {wins.map((a) => `${a.label} (${formatMetric(a, metricValue(you, a))})`).join(', ')}
        </p>
      )}
    </>
  )
}

/**
 * 0–100 (or 0–30 min) track with a honey band between two values: black dot = you, white dot = the other spot.
 * `compact` drops the labels under it.
 */
function GapBar({ attr, you, other, otherLabel, compact = false }) {
  const max = scaleMax(attr)
  const at = (v) => `${Math.min(100, Math.max(0, (v / max) * 100))}%`
  const lo = Math.min(you, other)
  const hi = Math.max(you, other)
  const labels = [
    { key: 'other', value: other, text: `${otherLabel} · ${formatMetric(attr, other)}` },
    { key: 'you', value: you, text: `You · ${formatMetric(attr, you)}` },
  ].sort((a, b) => a.value - b.value)

  return (
    <div className={`gap-bar${compact ? ' is-compact' : ''}`}>
      <div className="gap-track" role="img" aria-label={`You ${formatMetric(attr, you)}, ${otherLabel} ${formatMetric(attr, other)}`}>
        <span className="gap-band" style={{ left: at(lo), width: `calc(${at(hi)} - ${at(lo)})` }} />
        <span className="gap-dot is-other" style={{ left: at(other) }} />
        <span className="gap-dot is-you" style={{ left: at(you) }} />
      </div>
      {!compact && (
        <div className="gap-labels">
          {labels.map((l) => (
            <span key={l.key} className={l.key === 'you' ? 'is-you' : undefined}>
              {l.text}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------- Locked (consumer accounts) ----------

const SKELETON_ROWS = [64, 52, 72, 48, 60, 56]

/** The same layout, faded and inert, with no numbers: just shapes behind the "Business tools" card. */
function LockedHome({ onStart }) {
  return (
    <div className="biz locked-home">
      <div className="locked-preview" aria-hidden="true" inert>
        <Switch view="report" disabled />
        <section className="whoop is-skeleton">
          <span className="sk sk-line" style={{ width: '38%' }} />
          <span className="sk sk-title" />
          <span className="sk sk-line" style={{ width: '62%' }} />
          <div className="rings">
            {['Reputation', 'Momentum', 'Edge'].map((label) => (
              <Ring key={label} label={label} value={null} />
            ))}
          </div>
        </section>
        <h2 className="biz-label">Breakdown</h2>
        <ul className="breakdown">
          {SKELETON_ROWS.map((w, i) => (
            <li key={i}>
              <div className="breakdown-top">
                <span className="sk sk-line" style={{ width: `${w / 2}%` }} />
                <span className="sk sk-line" style={{ width: '24%' }} />
              </div>
              <div className="gap-bar is-compact">
                <div className="gap-track" />
              </div>
            </li>
          ))}
        </ul>
      </div>

      <section className="locked-card" aria-labelledby="locked-title">
        <span className="locked-icon">
          <IconLock />
        </span>
        <h2 id="locked-title">Business tools</h2>
        <p>Your report, insights and rivals are for business members.</p>
        <button className="locked-btn" onClick={onStart}>
          I run a spot
        </button>
      </section>
    </div>
  )
}
