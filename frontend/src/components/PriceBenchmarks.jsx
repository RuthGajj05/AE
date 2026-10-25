import { money } from '../format.js'

// Items priced above this (whole cakes, dozens) would squash everything else on a shared axis,
// so they're listed with their range but no bar.
const AXIS_CAP = 15

export function PriceBenchmarks({ benchmarks }) {
  const charted = benchmarks.filter((b) => b.max <= AXIS_CAP)
  const axisMax = Math.max(5, Math.ceil(Math.max(...charted.map((b) => b.max), 0) / 5) * 5)
  const pos = (v) => `${(v / axisMax) * 100}%`
  const ticks = Array.from({ length: axisMax / 5 + 1 }, (_, i) => i * 5)

  return (
    <div className="glass bench">
      <div className="bench-legend" aria-hidden="true">
        <span><i className="bench-key" />Price range across shops</span>
      </div>
      <ul className="bench-list">
        {benchmarks.map((b) => {
          const inAxis = b.max <= AXIS_CAP
          const range = b.min === b.max ? money(b.min) : `${money(b.min)} – ${money(b.max)}`
          return (
            <li key={b.id} className="bench-row">
              <div className="bench-label">
                <span className="bench-item">{b.item}</span>
                {b.note && <span className="bench-note">{b.note}</span>}
              </div>
              <div className="bench-plot">
                {inAxis ? (
                  <div className="bench-track" role="img" aria-label={`${b.item}: ${range}`}>
                    {ticks.map((t) => (
                      <span key={t} className="bench-grid" style={{ left: pos(t) }} />
                    ))}
                    <span className="bench-range" style={{ left: pos(b.min), width: `calc(${pos(b.max)} - ${pos(b.min)})` }} />
                    <span className="bench-dot" style={{ left: pos(b.min) }} />
                    {b.max !== b.min && <span className="bench-dot" style={{ left: pos(b.max) }} />}
                  </div>
                ) : (
                  <div className="bench-track is-off" />
                )}
                <span className="bench-value">{range}</span>
              </div>
            </li>
          )
        })}
      </ul>
      {charted.length > 0 && (
        <div className="bench-axis" aria-hidden="true">
          <span />
          <div className="bench-axis-scale">
            {ticks.map((t) => (
              <span key={t} style={{ left: pos(t) }}>${t}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
