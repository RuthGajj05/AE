import { useEffect, useState } from 'react'
import { BottomNav } from './BottomNav.jsx'
import { BusinessScreen } from './BusinessScreen.jsx'
import { MapScreen } from './MapScreen.jsx'
import { TABS } from './tabs.js'

const tabFromHash = () => {
  const id = window.location.hash.replace('#/', '')
  return TABS.some((t) => t.id === id) ? id : 'map'
}

export default function CrumbsApp() {
  const [tab, setTab] = useState(tabFromHash)

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  return (
    <div className="crumbs">
      {/* The map stays mounted so switching tabs doesn't reload it or re-run the Places search. */}
      <main className="screen" hidden={tab !== 'map'}>
        <MapScreen active={tab === 'map'} />
      </main>
      {tab === 'you' && (
        <main className="screen">
          <BusinessScreen />
        </main>
      )}
      {tab !== 'map' && tab !== 'you' && (
        <main className="screen empty-tab">
          <h1>{TABS.find((t) => t.id === tab).label}</h1>
          <p>Coming soon.</p>
        </main>
      )}
      <BottomNav current={tab} />
    </div>
  )
}
