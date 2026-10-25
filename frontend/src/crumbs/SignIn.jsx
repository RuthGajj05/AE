import { useState } from 'react'
import { signIn, signUp } from './auth.js'

/**
 * Email + password sign-in for business owners, inside the onboarding sheet. `onSignedIn` runs once Supabase has a
 * session (the AuthProvider picks it up too).
 */
export function SignIn({ titleId, onSignedIn, onCancel }) {
  const [mode, setMode] = useState('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sentTo, setSentTo] = useState(null)
  const creating = mode === 'signup'

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const result = creating ? await signUp(email.trim(), password) : await signIn(email.trim(), password)
    setBusy(false)
    if (!result.ok) return setError(result.error)
    if (result.confirm) {
      setSentTo(email.trim())
      setMode('signin')
      return
    }
    onSignedIn()
  }

  return (
    <>
      <span className="onb-tag">Business</span>
      <h2 id={titleId}>{creating ? 'Create your account' : 'Sign in to your spot'}</h2>
      <p className="onb-lede">
        {creating
          ? 'One account per business. You can browse the map without one.'
          : 'Sign in to set up your spot, see your report and get alerts about spots near you.'}
      </p>

      {sentTo && (
        <p className="onb-notice" role="status">
          We sent a confirmation link to {sentTo}. Open it, then sign in here.
        </p>
      )}

      <form onSubmit={submit} aria-labelledby={titleId}>
        <label className="onb-field">
          <span>Email</span>
          <input
            id="signin-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            autoFocus
          />
        </label>
        <label className="onb-field">
          <span>Password</span>
          <input
            id="signin-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={creating ? 'new-password' : 'current-password'}
            minLength={6}
            required
          />
        </label>
        {error && (
          <p className="onb-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="onb-primary" disabled={busy}>
          {busy ? 'One moment…' : creating ? 'Create account' : 'Sign in'}
        </button>
        <button
          type="button"
          className="onb-secondary"
          onClick={() => {
            setMode(creating ? 'signin' : 'signup')
            setError(null)
          }}
        >
          {creating ? 'I already have an account' : 'Create an account'}
        </button>
        <button type="button" className="onb-secondary" onClick={onCancel}>
          Not now
        </button>
      </form>
    </>
  )
}
