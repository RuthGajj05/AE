import { count, stars } from '../format.js'
import { IconPin } from './Icons.jsx'

function StarBar({ rating }) {
  const fill = rating === null ? 0 : (rating / 5) * 100
  return (
    <span className="star-bar" aria-hidden="true">
      <span className="star-bar-empty">★★★★★</span>
      <span className="star-bar-fill" style={{ width: `${fill}%` }}>★★★★★</span>
    </span>
  )
}

export function BusinessHeader({ business, updatedAt }) {
  const { name, type, area, rating, reviewCount } = business
  const updated = updatedAt?.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })

  return (
    <header className="hero">
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
        {updated && <p className="hero-updated">Updated {updated}</p>}
      </div>
      <div className="hero-rating" aria-label={rating === null ? 'No rating yet' : `Rated ${stars(rating)} out of 5`}>
        <span className="hero-rating-value">{stars(rating)}</span>
        <div>
          <StarBar rating={rating} />
          <span className="hero-rating-count">{reviewCount === null ? 'No reviews yet' : `${count(reviewCount)} reviews`}</span>
        </div>
      </div>
    </header>
  )
}
