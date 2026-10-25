import { useEffect, useMemo, useState } from 'react'
import { AuthContext, supabase } from './auth.js'

/** Keeps the Supabase session for the whole app; Supabase itself stores it in this browser. */
export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [ready, setReady] = useState(!supabase)

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setReady(true)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])

  const value = useMemo(() => ({ enabled: Boolean(supabase), ready, user: session?.user ?? null }), [ready, session])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
