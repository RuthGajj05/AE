import { useEffect, useRef, useState } from 'react'
import { IconPhone, IconSaved, IconShare } from './icons.jsx'
import { isScore, mentionText } from './metrics.js'
import { directionsUrl, isSaved, recordPick, toggleSaved } from './places.js'

const snapshotOf = (spot, cuisine) => ({
  id: spot.id,
  cuisine: cuisine.id,
  name: spot.name,
  price: spot.price,
  bestAt: spot.bestAt,
  reason: spot.reason,
  lat: spot.lat,
  lng: spot.lng,
})

/** Consumer "go here" view for one spot: key stats, ambiance, and the Go here / Save / Call / Share actions. */
export function GoHere({ spot, cuisine }) {
  const [saved, setSaved] = useState(() => isSaved(spot.id))
  const [copied, setCopied] = useState(false)
  const copiedTimer = useRef(null)
  const url = directionsUrl(spot)
  const topTwo = cuisine.attributes
    .filter(isScore)
    .sort((a, b) => spot.scores[b.id] - spot.scores[a.id])
    .slice(0, 2)

  useEffect(() => () => clearTimeout(copiedTimer.current), [])

  async function share() {
    const text = `${spot.name} on crumbs`
    try {
      if (navigator.share) {
        await navigator.share({ title: spot.name, text, url })
      } else {
        await navigator.clipboard.writeText(`${text}: ${url}`)
        setCopied(true)
        clearTimeout(copiedTimer.current)
        copiedTimer.current = setTimeout(() => setCopied(false), 2000)
      }
    } catch {
      // Share sheet closed or clipboard blocked: nothing to do.
    }
  }

  return (
    <div className="go">
      <h2 className="go-name">{spot.name}</h2>
      <p className="go-meta">
        {spot.price} · {spot.street} · Open until {spot.openUntil}
      </p>

      <div className="go-tiles">
        {topTwo.map((a) => (
          <div className="go-tile" key={a.id}>
            <span className="go-tile-num">{spot.scores[a.id]}</span>
            <span className="chip-label">{a.label}</span>
          </div>
        ))}
        <div className="go-tile">
          <span className="go-tile-num">
            {spot.waitMinutes}
            <small> min</small>
          </span>
          <span className="chip-label">Wait</span>
        </div>
      </div>

      <p className="go-ambiance">
        <b>Ambiance:</b> {spot.ambiancePct}% positive · {mentionText(spot.ambianceMentionRate)}
      </p>

      <a
        className="go-btn"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => recordPick({ cuisine: cuisine.id, chosenSpotId: spot.id, comparedSpotIds: cuisine.spots.map((s) => s.id) })}
      >
        Go here <span>· opens Google Maps</span>
      </a>

      <div className="go-actions">
        <button className={saved ? 'is-on' : undefined} aria-pressed={saved} onClick={() => setSaved(toggleSaved(spot.id, snapshotOf(spot, cuisine)))}>
          <IconSaved size={20} />
          {saved ? 'Saved' : 'Save'}
        </button>
        <a href={`tel:${spot.phone.replace(/[^\d+]/g, '')}`}>
          <IconPhone />
          Call
        </a>
        <button onClick={share}>
          <IconShare />
          {copied ? 'Copied' : 'Share'}
        </button>
      </div>

      <p className="go-note">Your pick is shared anonymously to help local spots improve.</p>
    </div>
  )
}
