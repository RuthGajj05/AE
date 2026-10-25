import { useEffect, useRef, useState } from 'react'
import { isBusiness, useAccount } from './account.js'
import { AccountProvider } from './AccountProvider.jsx'
import { BottomNav } from './BottomNav.jsx'
import { HomeScreen } from './HomeScreen.jsx'
import { MapScreen } from './MapScreen.jsx'
import { Onboarding } from './Onboarding.jsx'
import { TABS } from './tabs.js'

// #/home, #/alerts, #/map, #/saved, #/you. No (or an unknown) hash lands consumers on the Map, businesses on Home.
const tabFromHash = (business) => {
  const id = window.location.hash.replace('#/', '')
  if (TABS.some((t) => t.id === id)) return id
  return business ? 'home' : 'map'
}

export default function CrumbsApp() {
  return (
    <AccountProvider>
      <Shell />
    </AccountProvider>
  )
}

function Shell() {
  const { account, onboarding } = useAccount()
  const business = isBusiness(account)
  const [tab, setTab] = useState(() => tabFromHash(business))
  const businessNow = useRef(business)

  useEffect(() => {
    businessNow.current = business
  })

  useEffect(() => {
    const onHash = () => setTab(tabFromHash(businessNow.current))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  return (
    <div className="crumbs">
      {/* The map stays mounted so switching tabs doesn't reload it or re-run the Places search. */}
      <main className="screen" hidden={tab !== 'map'}>
        <MapScreen active={tab === 'map'} />
      </main>
      {tab === 'home' && (
        <main className="screen">
          <HomeScreen />
        </main>
      )}
      {(tab === 'alerts' || tab === 'saved' || tab === 'you') && (
        <main className="screen empty-tab">
          <h1>{TABS.find((t) => t.id === tab).label}</h1>
          <p>Coming soon.</p>
        </main>
      )}
      <BottomNav current={tab} />
      {onboarding && <Onboarding onDone={() => (window.location.hash = '#/home')} />}
    </div>
  )
}
