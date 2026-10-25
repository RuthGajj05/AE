import { useEffect, useId, useState } from 'react'
import { useAuth } from './auth.js'
import { SAMPLE_BUSINESS, useAccount } from './account.js'
import './onboarding.css'
import { getMe, matchCuisine, onboardBusiness, refreshAdvisorReport } from './places.js'
import { SalesConnect } from './SalesConnect.jsx'
import { SignIn } from './SignIn.jsx'

// Quick picks for "What kind of business?". Any text works; crumbs' food types (sushi, ramen, …) also get
// review scoring for Insights and Rivals.
const QUICK_TYPES = ['Bakery', 'Café', 'Coffee shop', 'Sushi', 'Ramen', 'Pizza', 'Tacos', 'Steak', 'Bar', 'Dessert']

/** Older accounts stored only a food type; show it in words. */
const typeOf = (business) => business?.type ?? (business?.cuisine ? business.cuisine[0].toUpperCase() + business.cuisine.slice(1) : '')

/**
 * "I run a spot": sign in (when sign-in is on), describe the spot, then optionally connect its sales. The backend
 * researches nearby competitors and writes the report once the sales step is done or skipped.
 */
export function Onboarding({ onDone }) {
  const { account, update, closeOnboarding } = useAccount()
  const { enabled: authOn, ready, user } = useAuth()
  const [form, setForm] = useState(() => {
    const b = account.business ?? SAMPLE_BUSINESS
    return { name: b.name, address: b.address, type: typeOf(b) }
  })
  const [step, setStep] = useState('details') // details | saving | sales
  const [businessId, setBusinessId] = useState(null)
  const [error, setError] = useState(null)
  const titleId = useId()
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  function finish() {
    closeOnboarding()
    onDone()
  }

  // Leaving the sales step without connecting still gets the owner a report (from competitor research alone).
  function skipSales() {
    refreshAdvisorReport(businessId)
    finish()
  }

  function close() {
    if (step === 'sales') return skipSales()
    closeOnboarding()
  }

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // After signing in: an owner who already set up a spot (e.g. on another device) gets it back and skips the form.
  async function afterSignIn() {
    const me = await getMe()
    if (me?.business) {
      update({ type: 'business', business: me.business })
      finish()
    }
  }

  async function submit(e) {
    e.preventDefault()
    const type = form.type.trim()
    if (!type) return setError('Tell us what kind of business it is, like bakery, cafe or sushi.')
    const business = {
      name: form.name.trim() || SAMPLE_BUSINESS.name,
      address: form.address.trim() || SAMPLE_BUSINESS.address,
      type,
      cuisine: matchCuisine(type),
    }
    // Same spot as before: keep its backend id and report. A new or edited spot is registered again.
    const unchanged = account.business && ['name', 'address'].every((k) => account.business[k] === business[k]) &&
      typeOf(account.business) === type
    if (unchanged) {
      update({ type: 'business' })
      return finish()
    }
    update({ type: 'business', business })
    // Register with the backend. Offline, it stays a local account with sample data.
    setStep('saving')
    setError(null)
    const r = await onboardBusiness(business, { advisorReport: false })
    if (!r?.businessId) return finish()
    update({ business: { ...business, id: r.businessId } })
    setBusinessId(r.businessId)
    setStep('sales')
  }

  let body
  if (authOn && ready && !user) {
    body = <SignIn titleId={titleId} onSignedIn={afterSignIn} onCancel={closeOnboarding} />
  } else if (step === 'sales') {
    body = (
      <>
        <span className="onb-tag">Optional</span>
        <h2 id={titleId}>Connect your sales</h2>
        <p className="onb-lede">
          With your sales, your report compares your prices and best sellers with nearby spots and estimates what each tip
          is worth. You can do this later from the You tab.
        </p>
        <SalesConnect businessId={businessId} onDone={finish} />
        <button type="button" className="onb-secondary" onClick={skipSales}>
          Skip for now
        </button>
      </>
    )
  } else {
    const matched = matchCuisine(form.type)
    body = (
      <>
        <span className="onb-tag">Business</span>
        <h2 id={titleId}>Set up your spot</h2>
        <p className="onb-lede">We'll research the spots near you and write your report (about a minute).</p>

        <form onSubmit={submit}>
          <label className="onb-field">
            <span>Spot name</span>
            <input id="onb-name" value={form.name} onChange={set('name')} autoComplete="organization" autoFocus />
          </label>
          <label className="onb-field">
            <span>Address</span>
            <input id="onb-address" value={form.address} onChange={set('address')} autoComplete="street-address" />
          </label>
          <label className="onb-field">
            <span>What kind of business?</span>
            <input id="onb-type" value={form.type} onChange={set('type')} placeholder="e.g. bakery, cafe, sushi bar" maxLength={60} />
          </label>
          <div className="onb-types" role="group" aria-label="Quick picks">
            {QUICK_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                className={form.type.toLowerCase() === t.toLowerCase() ? 'is-on' : undefined}
                onClick={() => setForm((f) => ({ ...f, type: t }))}
              >
                {t}
              </button>
            ))}
          </div>
          <p className="onb-note">
            {matched
              ? 'Your report, alerts, and crumbs Insights and Rivals for this food type.'
              : 'Your report and alerts. Insights and Rivals cover crumbs’ food types (sushi, ramen, pizza, tacos, steak) for now.'}
          </p>
          {error && (
            <p className="onb-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="onb-primary" disabled={step === 'saving'}>
            {step === 'saving' ? 'Setting up…' : 'Create business account'}
          </button>
          <button type="button" className="onb-secondary" onClick={closeOnboarding}>
            Not now
          </button>
        </form>
      </>
    )
  }

  return (
    <div className="onb-backdrop" onClick={close}>
      <section className="onb" role="dialog" aria-modal="true" aria-labelledby={titleId} onClick={(e) => e.stopPropagation()}>
        <span className="onb-handle" aria-hidden="true" />
        {body}
      </section>
    </div>
  )
}
