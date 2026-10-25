import { useState } from 'react'
import { count, stars } from '../format.js'
import { IconPin, IconSparkle } from './Icons.jsx'

function StarBar({ rating }) {
  return (
    <span className="star-bar" aria-hidden="true">
      <span className="star-bar-empty">★★★★★</span>
      <span className="star-bar-fill" style={{ width: `${(rating / 5) * 100}%` }}>★★★★★</span>
    </span>
  )
}

export function BusinessHeader({ business, summary, reportDate, dateOnly }) {
  const { name, type, area, rating, reviewCount } = business
  const [expanded, setExpanded] = useState(false)
  const when = reportDate?.toLocaleString(
    [],
    dateOnly ? { month: 'long', day: 'numeric', year: 'numeric' } : { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' },
  )

  return (
    <header className="hero">
      <div className="hero-top">
        <div className="hero-main">
          {(type || area) && (
            <p className="hero-eyebrow">
              {type && <span className="tag">{type}</span>}
              {area && (
                <span className="hero-area">
                  <IconPin />
                  {area}
                </span>
              )}
            </p>
          )}
          <h1>{name}</h1>
          {when && <p className="hero-updated">Competitor report · {when}</p>}
        </div>
        {rating !== null && (
          <div className="hero-rating" aria-label={`Rated ${stars(rating)} out of 5`}>
            <span className="hero-rating-value">{stars(rating)}</span>
            <div>
              <StarBar rating={rating} />
              {reviewCount !== null && <span className="hero-rating-count">{count(reviewCount)} reviews</span>}
            </div>
          </div>
        )}
      </div>

      {summary && (
        <div className="glass summary">
          <span className="summary-label">
            <IconSparkle size={14} />
            Market summary
          </span>
          <p className={expanded ? undefined : 'clamped'}>{summary}</p>
          <button className="text-btn" onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
            {expanded ? 'Show less' : 'Read the full summary'}
          </button>
        </div>
      )}
    </header>
  )
}
