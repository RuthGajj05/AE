import { useEffect, useState } from 'react'
import { formatMetric, isWait, mentionText, metricValue, scaleMax } from './metrics.js'
import { getBusinessReport } from './places.js'

const VIEWS = [
  { id: 'rivals', label: 'Rivals' },
  { id: 'insights', label: 'Insights' },
]

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

/** The You tab: the business side of crumbs. Rivals = picks lost and why; Insights = how you compare nearby. */
export function BusinessScreen() {
  const [view, setView] = useState('rivals')
  const [report, setReport] = useState(null)

  // Mounted fresh on every visit to the tab, so new Go-here picks show up.
  useEffect(() => {
    let live = true
    getBusinessReport().then((r) => live && setReport(r))
    return () => {
      live = false
    }
  }, [])

  return (
    <div className="biz">
      <div className="biz-switch" role="tablist" aria-label="Business views">
        {VIEWS.map((v) => (
          <button key={v.id} role="tab" aria-selected={view === v.id} className={view === v.id ? 'is-on' : undefined} onClick={() => setView(v.id)}>
            {v.label}
          </button>
        ))}
      </div>
      {report && (view === 'rivals' ? <Rivals report={report} /> : <Insights report={report} />)}
    </div>
  )
}

function Header({ title, report }) {
  return (
    <header className="biz-head">
      <h1>{title}</h1>
      <p>
        {report.you.name} · {report.cuisine.label} · {report.area} · {report.period}
        <span className="sample-tag">sample data</span>
      </p>
    </header>
  )
}

function Rivals({ report }) {
  const { you, rivals, wins, biggestGapId } = report
  return (
    <>
      <Header title="Rivals" report={report} />

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

function Insights({ report }) {
  const { you, breakdown, drag } = report
  return (
    <>
      <Header title="Insights" report={report} />

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

      <h2 className="biz-label">Breakdown</h2>
      <ul className="breakdown">
        {breakdown.map((row) => (
          <li key={row.attr.id}>
            <div className="breakdown-top">
              <span className="breakdown-name">{row.attr.label}</span>
              <span className="breakdown-value">
                {row.attr.id === 'ambiance'
                  ? `${row.you}% positive · ${mentionText(you.ambianceMentionRate)}`
                  : `${formatMetric(row.attr, row.you)} · area ${formatMetric(row.attr, row.area)}`}
              </span>
            </div>
            <GapBar attr={row.attr} you={row.you} other={row.area} otherLabel="Area" compact />
            {isWait(row.attr) && <p className="breakdown-note">Shorter is better</p>}
          </li>
        ))}
      </ul>
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
