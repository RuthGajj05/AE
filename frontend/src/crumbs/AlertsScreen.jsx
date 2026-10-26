import { checkCompetitorsNow } from './places.js'
import { useState } from 'react'
import { alertKindOn, isBusiness, useAccount } from './account.js'
import './alerts.css'
import { AlertIcon, IconPin, IconSearch } from './icons.jsx'

// Each chip covers the consumer kind and the matching owner kinds from the backend.
const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'fresh', label: 'Fresh in', kinds: ['fresh_stock'] },
  { id: 'top', label: 'Top rated', kinds: ['top_rated', 'rating_change'] },
  { id: 'price', label: 'Price', kinds: ['price_change'] },
  { id: 'new', label: 'New spots', kinds: ['new_spot', 'new_competitor'] },
]
const YOURS = { id: 'yours', label: 'Your spot' }

/** "12m", "3h", "yesterday", "4d" */
function timeAgo(iso) {
  const minutes = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000))
  if (minutes < 1) return 'now'
  if (minutes < 60) return `${minutes}m`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h`
  return hours < 48 ? 'yesterday' : `${Math.round(hours / 24)}d`
}

/** Alerts tab: what changed at spots nearby, plus owner alerts for business accounts. Tap opens the spot on the map. */
export function AlertsScreen({ feed, onOpen }) {
  const { account } = useAccount()
  const business = isBusiness(account)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [areaMenu, setAreaMenu] = useState(false)
  const [locateError, setLocateError] = useState('')
  const [reminders, setReminders] = useState(() => new Set())
  const [check, setCheck] = useState(null) // null | { busy } | { note } | { error }
  const businessId = business ? account.business.id : null

  // The monitor re-researches your competitors (about a minute); then the feed is asked again.
  async function checkNow() {
    setCheck({ busy: true })
    const r = await checkCompetitorsNow(businessId)
    if (!r.ok) return setCheck({ error: r.error })
    setCheck({ busy: true, note: 'Checking your competitors… about a minute. New changes show up here and in your email.' })
    setTimeout(() => {
      feed.reload()
      setCheck({ note: 'Done. If anything changed since the last check, it’s under Your spot.' })
    }, 75000)
  }

  const filters = business ? [...FILTERS, YOURS] : FILTERS
  const active = filters.find((f) => f.id === filter) ?? FILTERS[0]
  const q = query.trim().toLowerCase()
  const shown = feed.alerts
    .filter((a) => alertKindOn(account, a.kind))
    .filter((a) => !q || `${a.title} ${a.detail} ${a.cuisine ?? ''}`.toLowerCase().includes(q))
    .filter((a) => !active.kinds || active.kinds.includes(a.kind))
  const yours = business ? shown.filter((a) => a.audience === 'business') : []
  const nearby = filter === 'yours' ? [] : shown.filter((a) => a.audience !== 'business')

  function tap(alert) {
    feed.markRead(alert.id)
    if (alert.spotId || alert.cuisine) onOpen(alert.cuisine, alert.spotId)
  }

  async function locateMe() {
    setAreaMenu(false)
    setLocateError('')
    try {
      await feed.locate()
    } catch {
      setLocateError('Location is off, so this shows Capitol Hill.')
    }
  }

  const card = (a) => (
    <li key={a.id} className={`alert${a.read ? '' : ' is-unread'}`}>
      <button className="alert-main" onClick={() => tap(a)}>
        <span className="alert-icon">
          <AlertIcon kind={a.kind} />
        </span>
        <span className="alert-copy">
          <span className="alert-title">{a.title}</span>
          <span className="alert-detail">{a.detail}</span>
        </span>
        <span className="alert-meta">
          <span>{timeAgo(a.createdAt)}</span>
          {!a.read && <span className="alert-dot" aria-label="Unread" />}
        </span>
      </button>
      {a.kind === 'low_stock' && (
        <button
          className={`alert-action${reminders.has(a.id) ? ' is-on' : ''}`}
          aria-pressed={reminders.has(a.id)}
          onClick={() => setReminders((r) => new Set(r).add(a.id))}
        >
          {reminders.has(a.id) ? 'Reminder set' : 'Restock reminder'}
        </button>
      )}
    </li>
  )

  return (
    <div className="alerts">
      <header className="alerts-head">
        <h1>Alerts</h1>
        <div className="area-wrap">
          <button className="area-chip is-button" aria-expanded={areaMenu} onClick={() => setAreaMenu((o) => !o)}>
            <IconPin />
            {feed.area.label}
          </button>
          {areaMenu && (
            <div className="area-menu" role="menu">
              <button role="menuitem" onClick={locateMe}>
                Use my location
              </button>
              <button
                role="menuitem"
                onClick={() => {
                  setAreaMenu(false)
                  feed.resetArea()
                }}
              >
                Capitol Hill
              </button>
            </div>
          )}
        </div>
      </header>
      {locateError && <p className="alerts-note">{locateError}</p>}

      <label className="search-pill alerts-search">
        <IconSearch />
        <input type="search" placeholder="Search alerts, spots or food" value={query} onChange={(e) => setQuery(e.target.value)} />
      </label>

      <div className="sort-chips alerts-filters" role="group" aria-label="Filter alerts">
        {filters.map((f) => (
          <button key={f.id} className={`sort-chip${filter === f.id ? ' is-on' : ''}`} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
            {f.label}
          </button>
        ))}
      </div>

      {businessId && (
        <div className="alerts-check">
          <button className="alerts-check-btn" onClick={checkNow} disabled={check?.busy}>
            {check?.busy ? 'Checking…' : 'Check my competitors now'}
          </button>
          {(check?.note || check?.error) && (
            <p className={check.error ? 'alerts-note is-error' : 'alerts-note'} role="status">
              {check.error ?? check.note}
            </p>
          )}
        </div>
      )}

      {yours.length > 0 && (
        <section aria-label="Your spot">
          <h2 className="biz-label">Your spot</h2>
          <ul className="alert-list">{yours.map(card)}</ul>
        </section>
      )}
      {nearby.length > 0 && (
        <section aria-label="Near you">
          {business && <h2 className="biz-label">Near you</h2>}
          <ul className="alert-list">{nearby.map(card)}</ul>
        </section>
      )}
      {!feed.loading && yours.length === 0 && nearby.length === 0 && <p className="alerts-empty">No alerts near you yet.</p>}
    </div>
  )
}
