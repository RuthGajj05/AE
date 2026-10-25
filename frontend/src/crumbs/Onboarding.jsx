import { useEffect, useId, useState } from 'react'
import { useAuth } from './auth.js'
import { SAMPLE_BUSINESS, useAccount } from './account.js'
import { FoodIcon } from './foodIcons.jsx'
import './onboarding.css'
import { CUISINES, getMe, onboardBusiness } from './places.js'
import { SignIn } from './SignIn.jsx'

/** "I run a spot": a short sheet that turns this account into a business account. */
export function Onboarding({ onDone }) {
  const { account, update, closeOnboarding } = useAccount()
  const { enabled: authOn, ready, user } = useAuth()
  const [form, setForm] = useState(() => account.business ?? SAMPLE_BUSINESS)
  const titleId = useId()
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && closeOnboarding()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [closeOnboarding])

  // After signing in: an owner who already set up a spot (e.g. on another device) gets it back and skips the form.
  async function afterSignIn() {
    const me = await getMe()
    if (me?.business) {
      update({ type: 'business', business: me.business })
      closeOnboarding()
      onDone()
    }
  }

  function submit(e) {
    e.preventDefault()
    const business = {
      name: form.name.trim() || SAMPLE_BUSINESS.name,
      address: form.address.trim() || SAMPLE_BUSINESS.address,
      cuisine: form.cuisine,
    }
    // Same spot as before: keep its backend id and report. A new or edited spot is registered again.
    const unchanged = ['name', 'address', 'cuisine'].every((k) => account.business?.[k] === business[k])
    const known = unchanged ? account.business : business
    update({ type: 'business', business: known })
    closeOnboarding()
    onDone()
    if (known.id) return
    // Register with the backend, which starts the competitor research and report. Offline: stays a local account.
    onboardBusiness(business).then((r) => {
      if (r?.businessId) update({ business: { ...business, id: r.businessId } })
    })
  }

  return (
    <div className="onb-backdrop" onClick={closeOnboarding}>
      <section className="onb" role="dialog" aria-modal="true" aria-labelledby={titleId} onClick={(e) => e.stopPropagation()}>
        <span className="onb-handle" aria-hidden="true" />
        {authOn && ready && !user ? (
          <SignIn titleId={titleId} onSignedIn={afterSignIn} onCancel={closeOnboarding} />
        ) : (
          <>
            <span className="onb-tag">Business</span>
            <h2 id={titleId}>Set up your spot</h2>
            <p className="onb-lede">See how crumbs users compare you with spots nearby, and why they pick someone else.</p>

            <form onSubmit={submit}>
              <label className="onb-field">
                <span>Spot name</span>
                <input value={form.name} onChange={set('name')} autoComplete="organization" autoFocus />
              </label>
              <label className="onb-field">
                <span>Address</span>
                <input value={form.address} onChange={set('address')} autoComplete="street-address" />
              </label>
              <fieldset className="onb-field">
                <legend>What you serve</legend>
                <div className="onb-foods">
                  {CUISINES.map(({ id, label }) => (
                    <label key={id} className={`onb-food${form.cuisine === id ? ' is-on' : ''}`}>
                      <input type="radio" name="cuisine" value={id} checked={form.cuisine === id} onChange={set('cuisine')} />
                      <FoodIcon id={id} size={18} />
                      {label}
                    </label>
                  ))}
                </div>
              </fieldset>
              <p className="onb-note">
                We'll research the spots near you and write your report (about a minute). Insights and rivals use sample
                data until you connect Square.
              </p>
              <button type="submit" className="onb-primary">
                Create business account
              </button>
              <button type="button" className="onb-secondary" onClick={closeOnboarding}>
                Not now
              </button>
            </form>
          </>
        )}
      </section>
    </div>
  )
}
