import { FoodIcon } from './foodIcons.jsx'
import { bestFirst, formatMetric, metricValue } from './metrics.js'

const OVERALL = { id: 'overall', label: 'Best overall' }

/** Ranked cards for one food type, sortable by overall or any attribute. */
export function SpotList({ cuisine, sort, onSort, onOpenSpot }) {
  const attr = cuisine.attributes.find((a) => a.id === sort) ?? OVERALL
  const value = (s) => (attr === OVERALL ? s.overall : metricValue(s, attr))
  const shown = (s) => (attr === OVERALL ? s.overall : formatMetric(attr, value(s)))
  const ranked = [...cuisine.spots].sort(bestFirst(attr, value))

  return (
    <>
      <div className="sort-chips" role="group" aria-label="Sort by">
        {[OVERALL, ...cuisine.attributes].map((o) => (
          <button key={o.id} className={`sort-chip${o.id === attr.id ? ' is-on' : ''}`} aria-pressed={o.id === attr.id} onClick={() => onSort(o.id)}>
            {o.label}
          </button>
        ))}
      </div>
      <ol className="spot-list">
        {ranked.map((s, i) => (
          <li key={s.id}>
            <button className={`spot-card${i === 0 ? ' is-top' : ''}`} onClick={() => onOpenSpot(s.id)}>
              <span className="spot-icon">
                <FoodIcon id={cuisine.id} size={24} />
              </span>
              <span className="spot-main">
                <span className="spot-name">
                  <span className="letter-badge">{s.letter}</span>
                  {s.name}
                </span>
                <span className="spot-meta">
                  {s.price} · {s.distanceMi} mi
                </span>
              </span>
              <span className="spot-score">{shown(s)}</span>
              <span className="spot-why">
                <span className={`best-badge${i === 0 ? ' is-top' : ''}`}>{s.bestAt}</span>
                {s.reason}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </>
  )
}
