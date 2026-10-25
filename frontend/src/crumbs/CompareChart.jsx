import { IconChevron, IconStar } from './icons.jsx'
import { formatMetric, isWait, metricTone, metricValue } from './metrics.js'

/** Shaded box for one value: black = best, honey milk = middle, pale = weakest. */
export function ScoreBox({ attr, value }) {
  return <span className={`score score-${metricTone(attr, value)}${isWait(attr) ? ' is-wide' : ''}`}>{formatMetric(attr, value)}</span>
}

/** Subtle one-line callout for the best-overall spot. */
export function PickRow({ cuisine, onOpenSpot }) {
  const pick = cuisine.spots.find((s) => s.pick)
  if (!pick) return null
  return (
    <button className="pick-row" onClick={() => onOpenSpot(pick.id)}>
      <span className="pick-star">
        <IconStar size={14} />
      </span>
      <span className="pick-copy">
        <span className="pick-label">crumbs pick</span>
        <span className="pick-text">
          <b>{pick.name}</b> · {cuisine.pickLine}
        </span>
      </span>
      <IconChevron />
    </button>
  )
}

/** Spots as columns, attributes as rows, one shaded box per cell. */
export function CompareChart({ cuisine, onOpenSpot }) {
  const { spots, attributes } = cuisine
  return (
    <div className="compare">
      <h3 className="sheet-label">Compare side by side</h3>
      <div className="compare-grid" role="table" aria-label={`${cuisine.label} spots compared`} style={{ '--cols': spots.length }}>
        <div className="compare-row" role="row">
          <span role="columnheader" />
          {spots.map((s) => (
            <span role="columnheader" key={s.id}>
              <button className="compare-spot" onClick={() => onOpenSpot(s.id)} aria-label={`Spot ${s.letter}, ${s.name}${s.pick ? ', crumbs pick' : ''}`}>
                Spot {s.letter}
                {s.pick && <IconStar size={10} />}
              </button>
            </span>
          ))}
        </div>
        {attributes.map((a) => (
          <div className="compare-row" role="row" key={a.id}>
            <span className="compare-attr" role="rowheader">
              {a.label}
            </span>
            {spots.map((s) => (
              <span className="compare-cell" role="cell" key={s.id}>
                <ScoreBox attr={a} value={metricValue(s, a)} />
              </span>
            ))}
          </div>
        ))}
      </div>
      <div className="legend">
        <span className="score-swatch score-low" />
        <span className="score-swatch score-mid" />
        <span className="score-swatch score-top" />
        <span>Darker = what reviewers rate best</span>
      </div>
      <p className="legend-note">Ambiance = % of mentions that are positive · Wait = avg minutes</p>
    </div>
  )
}
