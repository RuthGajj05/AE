import { average } from '../data/adapter.js'
import { comparableMetrics } from '../compareMetrics.js'
import { IconArrow } from './Icons.jsx'

/** Where you and every competitor fall on one line, so the average has context. */
function RangeStrip({ you, avg, values, format }) {
  const all = [...values, you]
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const pad = (hi - lo) * 0.08 || 1
  const pos = (v) => `${((v - (lo - pad)) / (hi - lo + 2 * pad)) * 100}%`

  return (
    <div className="strip" aria-hidden="true">
      <div className="strip-track" />
      {values.map((v, i) => (
        <span key={i} className="strip-dot" style={{ left: pos(v) }} title={format(v)} />
      ))}
      <span className="strip-avg" style={{ left: pos(avg) }} title={`Nearby average ${format(avg)}`} />
      <span className="strip-you" style={{ left: pos(you) }} title={`You ${format(you)}`} />
    </div>
  )
}

function CompareCard({ metric, business, competitors }) {
  const you = business[metric.key]
  const values = competitors.map((c) => c[metric.key]).filter((v) => v !== null)
  const avg = average(competitors, metric.key)
  const comparable = you !== null && avg !== null

  let tone = 'neutral'
  let dir = 'flat'
  let summary = comparable ? 'About the same' : 'Not enough data'
  if (comparable) {
    const text = metric.describe(you, avg)
    if (text) {
      dir = you > avg ? 'up' : 'down'
      tone = (you < avg) === metric.lowerIsBetter ? 'good' : 'bad'
      summary = text
    }
  }

  return (
    <article className="glass compare">
      <div className="compare-top">
        <span className="compare-label">{metric.label}</span>
        <span className={`delta delta-${tone}`}>
          <IconArrow dir={dir} />
          {summary}
        </span>
      </div>
      <div className="compare-values">
        <div>
          <span className="compare-you">{metric.format(you)}</span>
          <span className="compare-caption">
            <i className="key-you" />
            You
          </span>
        </div>
        <div className="compare-avg">
          <span>{metric.format(avg)}</span>
          <span className="compare-caption">
            <i className="key-avg" />
            Nearby avg
          </span>
        </div>
      </div>
      {comparable && values.length > 0 && <RangeStrip you={you} avg={avg} values={values} format={metric.format} />}
    </article>
  )
}

export function CompareCards({ business, competitors }) {
  return (
    <div className="compare-grid">
      {comparableMetrics(business, competitors).map((m) => (
        <CompareCard key={m.key} metric={m} business={business} competitors={competitors} />
      ))}
    </div>
  )
}
