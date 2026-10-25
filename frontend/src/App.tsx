import { useState } from 'react'
import { Dashboard } from './components/Dashboard'
import { ProfileForm } from './components/ProfileForm'
import { CATEGORIES, NEIGHBORHOODS } from './data/reference'
import { DEMO_PROFILE } from './data/sample'
import type { Profile } from './types'

const STORAGE_KEY = 'localedge.profile'

function loadProfile(): Profile | null {
  // `?demo` opens straight into the dashboard with the demo bakery, handy for showing the app.
  if (new URLSearchParams(window.location.search).has('demo')) return DEMO_PROFILE
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Profile) : null
  } catch {
    return null
  }
}

function saveProfile(p: Profile | null) {
  try {
    if (p) localStorage.setItem(STORAGE_KEY, JSON.stringify(p))
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage can be unavailable (private mode); the session still works.
  }
}

export default function App() {
  const [profile, setProfile] = useState<Profile | null>(loadProfile)
  const [editing, setEditing] = useState(false)

  const save = (p: Profile) => {
    saveProfile(p)
    setProfile(p)
    setEditing(false)
  }

  const reset = () => {
    saveProfile(null)
    setProfile(null)
    setEditing(false)
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden="true">LE</span>
          <div>
            <strong>LocalEdge</strong>
            <span className="muted">Market research for neighborhood food businesses</span>
          </div>
        </div>
        {profile && !editing && (
          <div className="topbar-actions">
            <button className="btn ghost" onClick={() => setEditing(true)}>Edit business</button>
            <button className="text-btn" onClick={reset}>Start over</button>
          </div>
        )}
      </header>

      <main className="content">
        {!profile || editing ? (
          <ProfileForm initial={profile} onSave={save} onCancel={profile ? () => setEditing(false) : undefined} />
        ) : (
          <>
            <div className="page-title">
              <h1>{profile.name}</h1>
              <p className="muted">
                {CATEGORIES[profile.category].label} · {NEIGHBORHOODS[profile.neighborhood].label}, Seattle
              </p>
            </div>
            <Dashboard profile={profile} />
          </>
        )}
        <p className="notice">
          Sample data: competitors and trends shown here are illustrative, fictional Seattle businesses. Live web
          research isn't connected yet.
        </p>
      </main>
    </div>
  )
}
