import { useEffect, useId, useState } from 'react'
import { SAMPLE_BUSINESS, useAccount } from './account.js'
import { FoodIcon } from './foodIcons.jsx'
import './onboarding.css'
import { CUISINES } from './places.js'

/** "I run a spot": a short sheet that turns this account into a business account. */
export function Onboarding({ onDone }) {
  const { account, update, closeOnboarding } = useAccount()
  const [form, setForm] = useState(() => account.business ?? SAMPLE_BUSINESS)
  const titleId = useId()
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && closeOnboarding()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [closeOnboarding])

  function submit(e) {
    e.preventDefault()
    update({
      type: 'business',
      business: {
        name: form.name.trim() || SAMPLE_BUSINESS.name,
        address: form.address.trim() || SAMPLE_BUSINESS.address,
        cuisine: form.cuisine,
      },
    })
    closeOnboarding()
    onDone()
  }

  return (
    <div className="onb-backdrop" onClick={closeOnboarding}>
      <section className="onb" role="dialog" aria-modal="true" aria-labelledby={titleId} onClick={(e) => e.stopPropagation()}>
        <span className="onb-handle" aria-hidden="true" />
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
          <p className="onb-note">Insights and rivals use sample data until you connect Square.</p>
          <button type="submit" className="onb-primary">
            Create business account
          </button>
          <button type="button" className="onb-secondary" onClick={closeOnboarding}>
            Not now
          </button>
        </form>
      </section>
    </div>
  )
}
