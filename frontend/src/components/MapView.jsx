import { useEffect, useMemo, useRef, useState } from 'react'
import { count, miles, money, stars } from '../format.js'
import { withLocations } from '../lib/spots.js'
import { LicenseBadge } from './LicenseBadge.jsx'
import { SpotMap } from './SpotMap.jsx'
import { EmptyState } from './States.jsx'

const plural = (word, n) => (n === 1 ? word : word.endsWith('y') ? `${word.slice(0, -1)}ies` : `${word}s`)

function SpotCard({ spot, index, active, onSelect, onHover, cardRef }) {
  return (
    <article
      ref={cardRef}
      className={`glass spot${active ? ' is-active' : ''}`}
      tabIndex={0}
      aria-current={active || undefined}
      onClick={() => onSelect(spot.id, 'list')}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onSelect(spot.id, 'list')
      }}
      onMouseEnter={() => onHover(spot.id)}
      onMouseLeave={() => onHover(null)}
    >
      <div className="spot-top">
        <span className="spot-index">{index + 1}</span>
        <div className="spot-heading">
          <h3>{spot.name}</h3>
          {spot.address && <p className="spot-address">{spot.address.replace(/, Seattle, WA/i, '')}</p>}
        </div>
        {spot.distanceMi !== null && <span className="spot-distance">{miles(spot.distanceMi)}</span>}
      </div>

      <div className="spot-stats">
        {spot.rating !== null && (
          <span>
            <span className="table-star">★</span>
            <strong>{stars(spot.rating)}</strong>
            {spot.reviewCount !== null && <span className="muted"> ({count(spot.reviewCount)})</span>}
          </span>
        )}
        {spot.minPrice !== null && (
          <span>
            Items from <strong>{money(spot.minPrice)}</strong>
          </span>
        )}
        {spot.topWeakness && <span className="weakness">{spot.topWeakness}</span>}
      </div>

      <LicenseBadge name={spot.name} address={spot.address} />
      {spot.lat === null && <p className="spot-nopin">No map location yet</p>}
    </article>
  )
}

export function MapView({ data }) {
  const spots = useMemo(() => withLocations(data.competitors), [data.competitors])
  const [activeId, setActiveId] = useState(null)
  const [hoverId, setHoverId] = useState(null)
  const cards = useRef(new Map())
  const lastPick = useRef(null)
  const placed = spots.filter((s) => s.lat !== null).length

  const select = (id, from) => {
    lastPick.current = from
    setActiveId((current) => (current === id && from === 'list' ? null : id))
  }

  // A pin click scrolls its card into view; a card click leaves the list where it is.
  useEffect(() => {
    if (activeId && lastPick.current === 'map') cards.current.get(activeId)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [activeId])

  if (!spots.length) {
    return (
      <div className="page">
        <EmptyState title="No spots to map yet" text="Load a competitor report to see nearby businesses on the map." />
      </div>
    )
  }

  return (
    <div className="map-layout">
      <section className="spot-list" aria-label="Nearby competitors">
        <header className="spot-list-head">
          <h1>
            {spots.length} {plural(data.business.type.toLowerCase() || 'spot', spots.length)} near {data.business.area || 'you'}
          </h1>
          <p>
            Tap a pin or a card · {placed} of {spots.length} on the map · licenses checked against Seattle's records
          </p>
        </header>
        <div className="spot-cards">
          {spots.map((spot, i) => (
            <SpotCard
              key={spot.id}
              spot={spot}
              index={i}
              active={spot.id === activeId}
              onSelect={select}
              onHover={setHoverId}
              cardRef={(el) => (el ? cards.current.set(spot.id, el) : cards.current.delete(spot.id))}
            />
          ))}
        </div>
      </section>
      <div className="map-pane">
        <SpotMap spots={spots} activeId={activeId} hoverId={hoverId} onSelect={select} />
      </div>
    </div>
  )
}
