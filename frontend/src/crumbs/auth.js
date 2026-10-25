import { createClient } from '@supabase/supabase-js'
import { createContext, useContext } from 'react'

// Sign-in for business owners: Supabase Auth, email + password. The URL and publishable key come from .env.local
// (VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY); both are safe in the browser. Without them, sign-in is off and
// the app works as before (the backend then doesn't ask for it either). Browsing never needs a sign-in.
const url = import.meta.env.VITE_SUPABASE_URL || ''
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || ''
export const supabase = url && key ? createClient(url, key) : null

export const AuthContext = createContext({ enabled: false, ready: true, user: null })

/** { enabled, ready, user } — user is Supabase's user ({ id, email, … }) or null when signed out. */
export const useAuth = () => useContext(AuthContext)

/** The current access token for backend calls, or null when signed out (or sign-in is off). */
export async function accessToken() {
  if (!supabase) return null
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

// Supabase's messages are fine for most cases; these read better in the app.
function friendly(error) {
  const msg = error?.message ?? ''
  if (/invalid login credentials/i.test(msg)) return "That email and password don't match. Try again, or create an account."
  if (/email not confirmed/i.test(msg)) return 'Confirm your email first: open the link we sent you, then sign in.'
  if (/already registered/i.test(msg)) return 'That email already has an account. Sign in instead.'
  if (/password/i.test(msg) && /(6|characters|weak)/i.test(msg)) return 'Use a password of at least 6 characters.'
  if (/fetch|network/i.test(msg)) return "We couldn't reach the sign-in service. Check your connection and try again."
  return msg || 'Something went wrong. Please try again.'
}

/** { ok: true } when signed in; { ok: false, error } otherwise. */
export async function signIn(email, password) {
  const { error } = await supabase.auth.signInWithPassword({ email, password })
  return error ? { ok: false, error: friendly(error) } : { ok: true }
}

/** { ok: true, confirm } — confirm: true when Supabase emailed a confirmation link before the first sign-in. */
export async function signUp(email, password) {
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: window.location.origin },
  })
  if (error) return { ok: false, error: friendly(error) }
  return { ok: true, confirm: !data.session }
}

export async function signOut() {
  await supabase?.auth.signOut()
}
