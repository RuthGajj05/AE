import { useRef, useState } from 'react'
import { FoodIcon } from './foodIcons.jsx'
import { IconX } from './icons.jsx'
import { getSavedSpots, removeSaved } from './places.js'
import './saved.css'

// How far left a card has to be swiped before letting go removes it.
const SWIPE_REMOVE = 90

/** Saved tab: spots the user tapped Save on. Tap opens Go here; swipe left or ✕ removes. */
export function SavedScreen({ onOpen }) {
  const [spots, setSpots] = useState(getSavedSpots)

  function remove(id) {
    removeSaved(id)
    setSpots((list) => list.filter((s) => s.id !== id))
  }

  return (
    <div className="saved">
      <h1>Saved</h1>
      {spots.length ? (
        <ul className="saved-list">
          {spots.map((spot) => (
            <SavedCard key={spot.id} spot={spot} onOpen={() => onOpen(spot.cuisine, spot.id)} onRemove={() => remove(spot.id)} />
          ))}
        </ul>
      ) : (
        <p className="saved-empty">Save spots from the map to find them here.</p>
      )}
    </div>
  )
}

function SavedCard({ spot, onOpen, onRemove }) {
  const [dx, setDx] = useState(0)
  const start = useRef(null)
  const swiped = useRef(false)

  const onPointerDown = (e) => {
    if (!e.isPrimary) return
    start.current = e.clientX
    swiped.current = false
  }
  const onPointerMove = (e) => {
    if (start.current === null) return
    const d = Math.min(0, e.clientX - start.current)
    if (d < -6) swiped.current = true
    if (swiped.current) setDx(d)
  }
  const onPointerEnd = () => {
    if (start.current === null) return
    start.current = null
    if (dx <= -SWIPE_REMOVE) onRemove()
    else setDx(0)
  }

  return (
    <li className="saved-item">
      <div
        className={`saved-card${dx ? ' is-swiping' : ''}`}
        style={dx ? { transform: `translateX(${dx}px)` } : undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd}
      >
        <button
          className="saved-main"
          onClick={() => {
            // A swipe that snapped back shouldn't also open the spot.
            if (swiped.current) return
            onOpen()
          }}
        >
          <span className="saved-icon">
            <FoodIcon id={spot.cuisine} size={24} />
          </span>
          <span className="saved-copy">
            <span className="saved-name">{spot.name}</span>
            <span className="saved-meta">
              {spot.price} · {spot.walk.miles} mi
            </span>
            <span className="saved-why">
              {spot.bestAt && <span className="best-badge">{spot.bestAt}</span>}
              {spot.reason}
            </span>
          </span>
        </button>
        <button className="saved-remove" onClick={onRemove} aria-label={`Remove ${spot.name}`}>
          <IconX />
        </button>
      </div>
    </li>
  )
}
