import { useEffect, useRef, useState } from 'react'
import { alertKindOn, isBusiness, useAccount } from './account.js'
import { AccountProvider } from './AccountProvider.jsx'
import { AlertsScreen } from './AlertsScreen.jsx'
import { BottomNav } from './BottomNav.jsx'
import { HomeScreen } from './HomeScreen.jsx'
import { MapScreen } from './MapScreen.jsx'
import { Onboarding } from './Onboarding.jsx'
import { SavedScreen } from './SavedScreen.jsx'
import { TABS } from './tabs.js'
import { useAlerts } from './useAlerts.js'
import { YouScreen } from './YouScreen.jsx'

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
  const mapControl = useRef(null)
  const alerts = useAlerts(business ? 'business' : 'consumer', account.business?.id)
  const unread = alerts.alerts.filter((a) => !a.read && alertKindOn(account, a.kind)).length

  useEffect(() => {
    businessNow.current = business
  })

  useEffect(() => {
    const onHash = () => setTab(tabFromHash(businessNow.current))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // From Alerts or Saved: switch to the Map and open that food type (and spot). The food type loads async, so the
  // map is already visible when it fits the pins.
  function openOnMap(cuisine, spotId) {
    setTab('map')
    mapControl.current?.openSpot(cuisine, spotId ?? null)
    window.location.hash = '#/map'
  }

  return (
    <div className="crumbs">
      {/* The map stays mounted so switching tabs doesn't reload it or re-run the Places search. */}
      <main className="screen" hidden={tab !== 'map'}>
        <MapScreen active={tab === 'map'} controlRef={mapControl} />
      </main>
      {tab === 'home' && (
        <main className="screen">
          <HomeScreen />
        </main>
      )}
      {tab === 'alerts' && (
        <main className="screen">
          <AlertsScreen feed={alerts} onOpen={openOnMap} />
        </main>
      )}
      {tab === 'saved' && (
        <main className="screen">
          <SavedScreen onOpen={openOnMap} />
        </main>
      )}
      {tab === 'you' && (
        <main className="screen">
          <YouScreen />
        </main>
      )}
      <BottomNav current={tab} badges={{ alerts: unread }} />
      {onboarding && <Onboarding onDone={() => (window.location.hash = '#/home')} />}
    </div>
  )
}
