import { useEffect, useState } from 'react'
import { signOut, useAuth } from './auth.js'
import { ALERT_KINDS, AREAS, alertKindOn, initials, isBusiness, useAccount } from './account.js'
import { FoodIcon } from './foodIcons.jsx'
import { IconChevron } from './icons.jsx'
import { CUISINES, getAlertSettings, matchCuisine, setAlertEmails } from './places.js'
import { SalesConnect } from './SalesConnect.jsx'
import './you.css'

/** You tab: profile and settings. Insights and Rivals live on Home. */
export function YouScreen() {
  const { account, update, startOnboarding } = useAccount()
  const { enabled: authOn, user } = useAuth()
  const business = isBusiness(account)
  const kinds = ALERT_KINDS.filter((k) => business || k.audience === 'consumer')
  const setBusiness = (patch) => update({ business: { ...account.business, ...patch } })

  function toggleFavorite(id) {
    const on = account.favorites.includes(id)
    update({ favorites: on ? account.favorites.filter((f) => f !== id) : [...account.favorites, id] })
  }

  function switchType(type) {
    if (type === 'business' && !account.business) return startOnboarding()
    update({ type })
  }

  return (
    <div className="you">
      <header className="you-head">
        <span className="you-avatar" aria-hidden="true">
          {initials(account.name)}
        </span>
        <div className="you-id">
          <p className="you-name">
            {account.name}
            {business ? <span className="badge-business">Business</span> : <span className="badge-member">Member</span>}
          </p>
          {business && <p className="you-spot">{account.business.name}</p>}
          <p className="you-area">{account.homeArea}</p>
        </div>
      </header>

      <div className="you-rows">
        {authOn && user && (
          <div className="you-row is-static">
            <span className="you-row-title">Signed in</span>
            <span className="you-signed">
              {user.email}
              <button
                className="you-signout"
                onClick={async () => {
                  await signOut()
                  update({ type: 'consumer', business: null })
                }}
              >
                Sign out
              </button>
            </span>
          </div>
        )}
        <Row title="Edit profile" detail={`${account.name} · ${account.homeArea}`}>
          <label className="you-field">
            <span>Name</span>
            <input value={account.name} onChange={(e) => update({ name: e.target.value })} autoComplete="name" />
          </label>
          <label className="you-field">
            <span>Home area</span>
            <select value={account.homeArea} onChange={(e) => update({ homeArea: e.target.value })}>
              {AREAS.map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </label>
        </Row>

        <Row title="Favorite foods" detail={account.favorites.length ? `${account.favorites.length} picked` : 'None yet'}>
          <div className="you-foods" role="group" aria-label="Favorite foods">
            {CUISINES.map(({ id, label }) => {
              const on = account.favorites.includes(id)
              return (
                <button key={id} className={`you-food${on ? ' is-on' : ''}`} aria-pressed={on} onClick={() => toggleFavorite(id)}>
                  <FoodIcon id={id} size={18} />
                  {label}
                </button>
              )
            })}
          </div>
        </Row>

        <Row title="Alert preferences" detail={`${kinds.filter((k) => alertKindOn(account, k.id)).length} of ${kinds.length} on`}>
          <ul className="you-toggles">
            {kinds.map((k) => {
              const on = alertKindOn(account, k.id)
              return (
                <li key={k.id}>
                  <span>{k.label}</span>
                  <button
                    role="switch"
                    aria-checked={on}
                    aria-label={k.label}
                    className={`switch${on ? ' is-on' : ''}`}
                    onClick={() => update({ alertPrefs: { ...account.alertPrefs, [k.id]: !on } })}
                  >
                    <span />
                  </button>
                </li>
              )
            })}
          </ul>
        </Row>

        <Row title="Switch account type" detail={business ? 'Business' : 'Member'}>
          <div className="you-type" role="radiogroup" aria-label="Account type">
            {[
              ['consumer', 'Member'],
              ['business', 'Business'],
            ].map(([type, label]) => (
              <button
                key={type}
                role="radio"
                aria-checked={(type === 'business') === business}
                className={(type === 'business') === business ? 'is-on' : undefined}
                onClick={() => switchType(type)}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="you-note">Business accounts see their report, Insights and Rivals on Home.</p>
        </Row>

        {business && (
          <>
            <Row title="Your spot" detail={account.business.name}>
              <label className="you-field">
                <span>Spot name</span>
                <input value={account.business.name} onChange={(e) => setBusiness({ name: e.target.value })} />
              </label>
              <label className="you-field">
                <span>Address</span>
                <input value={account.business.address} onChange={(e) => setBusiness({ address: e.target.value })} />
              </label>
              <label className="you-field">
                <span>Kind of business</span>
                <input
                  value={account.business.type ?? account.business.cuisine ?? ''}
                  onChange={(e) => setBusiness({ type: e.target.value, cuisine: matchCuisine(e.target.value) })}
                  placeholder="e.g. bakery, cafe, sushi bar"
                  maxLength={60}
                />
              </label>
            </Row>
            {account.business.id && (
              <Row title="Alert emails" detail="When competitors change">
                <AlertEmails businessId={account.business.id} />
              </Row>
            )}
            <Row title="Sales data" detail="CSV, Square or Toast">
              {account.business.id ? (
                <SalesConnect businessId={account.business.id} />
              ) : (
                <p className="you-note">
                  Your spot isn't set up with the crumbs backend yet. Set it up again from Home ("I run a spot"), then
                  connect your sales here.
                </p>
              )}
            </Row>
          </>
        )}
      </div>
    </div>
  )
}

/** The owner's alert emails: on/off, where they go, and whether the last few were delivered. */
function AlertEmails({ businessId }) {
  const [settings, setSettings] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    getAlertSettings(businessId).then((r) => live && (r.ok ? setSettings(r.data) : setError(r.error)))
    return () => {
      live = false
    }
  }, [businessId])

  async function toggle(e) {
    const r = await setAlertEmails(businessId, e.target.checked)
    if (r.ok) setSettings(r.data)
    else setError(r.error)
  }

  if (error) return <p className="you-note">{error}</p>
  if (!settings) return <p className="you-note">Loading…</p>
  return (
    <div className="you-emails">
      <label className="you-check">
        <input id="alert-emails" type="checkbox" checked={settings.emailAlerts} onChange={toggle} />
        Email me when a competitor opens, closes, or changes prices or hours
      </label>
      <p className="you-note">
        {settings.ownerEmail ? `Sent to ${settings.ownerEmail}.` : 'Sign in when you set up your spot to get emails.'}
      </p>
      {settings.recentEmails.length > 0 && (
        <ul className="you-email-log">
          {settings.recentEmails.map((m, i) => (
            <li key={i}>
              <span className={`you-email-status is-${m.status}`}>{m.status}</span> {m.subject}
              {m.detail && <span className="you-note"> · {m.detail}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Row({ title, detail, children }) {
  return (
    <details className="you-row">
      <summary>
        <span className="you-row-title">{title}</span>
        <span className="you-row-detail">{detail}</span>
        <IconChevron />
      </summary>
      <div className="you-row-body">{children}</div>
    </details>
  )
}
