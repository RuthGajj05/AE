import { useEffect, useState } from 'react'
import { FoodButtons } from './FoodChips.jsx'
import { IconPin, IconSearch, IconStar } from './icons.jsx'
import { formatPrice, getPlaceScores } from './places.js'

const SCORES = [
  ['freshness', 'Freshness'],
  ['value', 'Value'],
  ['service', 'Service'],
]

/**
 * Default Waze-style sheet above the nav: search pill and "Popular near you" food buttons. A tapped map spot
 * shows its details in place of the food buttons.
 */
export function SearchSheet({ place, query, onQuery, onCollapse, onCuisine, sheetRef }) {
  useEffect(() => {
    if (!place) return
    const onKey = (e) => e.key === 'Escape' && onCollapse()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [place, onCollapse])

  return (
    <section ref={sheetRef} className="sheet search-sheet" aria-label="Search">
      <button className="sheet-handle" onClick={onCollapse} aria-label="Collapse" tabIndex={place ? 0 : -1}>
        <span />
      </button>
      <label className="search-pill">
        <IconSearch />
        <input type="search" placeholder="Search a spot or cuisine" value={query} onChange={(e) => onQuery(e.target.value)} />
      </label>
      {place ? (
        <PlaceDetails key={place.id} place={place} />
      ) : (
        <>
          <p className="sheet-label">Popular near you</p>
          <FoodButtons onSelect={onCuisine} />
        </>
      )}
    </section>
  )
}

/** Scores stay "—" until the review analysis exists. */
function PlaceDetails({ place }) {
  const [scores, setScores] = useState(null)
  const price = formatPrice(place.priceLevel)

  useEffect(() => {
    let live = true
    getPlaceScores(place.id).then((s) => live && setScores(s))
    return () => {
      live = false
    }
  }, [place.id])

  return (
    <div className="place">
      <h2>{place.name}</h2>
      <p className="place-meta">
        <span>{place.cuisine}</span>
        {price && <span>{price}</span>}
        {place.rating !== null && (
          <span className="place-rating">
            <IconStar />
            {place.rating.toFixed(1)}
            {place.ratingCount !== null && <span className="place-count">({place.ratingCount.toLocaleString()})</span>}
          </span>
        )}
      </p>
      {place.address && (
        <p className="place-address">
          <IconPin />
          {place.address}
        </p>
      )}
      <div className="place-chips">
        {SCORES.map(([key, label]) => (
          <div className="chip" key={key}>
            <span className="chip-label">{label}</span>
            <span className="chip-value">{scores?.[key] ?? '—'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
