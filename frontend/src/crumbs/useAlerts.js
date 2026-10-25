import { useCallback, useEffect, useState } from 'react'
import { CAPITOL_HILL, getAlerts, markAlertRead } from './places.js'

const DEFAULT_AREA = { label: 'Capitol Hill', ...CAPITOL_HILL, current: false }

/**
 * The alerts feed for the whole app (the Alerts tab and its unread badge). Uses the user's location only if they
 * already allowed it, or tap "Use my location"; otherwise Capitol Hill.
 */
export function useAlerts(audience, businessId) {
  const [area, setArea] = useState(DEFAULT_AREA)
  const [feed, setFeed] = useState({ alerts: [], isSample: true, loading: true })
  const [reloads, setReloads] = useState(0)

  const locate = useCallback(
    () =>
      new Promise((resolve, reject) => {
        if (!navigator.geolocation) return reject(new Error('No location on this device.'))
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            setArea({ label: 'Current location', lat: pos.coords.latitude, lng: pos.coords.longitude, current: true })
            resolve()
          },
          reject,
          { timeout: 8000, maximumAge: 5 * 60 * 1000 },
        )
      }),
    [],
  )

  // Already allowed? Use it without asking. Never prompt on load.
  useEffect(() => {
    navigator.permissions
      ?.query({ name: 'geolocation' })
      .then((p) => p.state === 'granted' && locate())
      .catch(() => {})
  }, [locate])

  useEffect(() => {
    let live = true
    getAlerts({ lat: area.lat, lng: area.lng, audience, businessId }).then((r) => live && setFeed({ ...r, loading: false }))
    return () => {
      live = false
    }
  }, [area, audience, businessId, reloads])

  const markRead = useCallback((id) => {
    markAlertRead(id)
    setFeed((f) => ({ ...f, alerts: f.alerts.map((a) => (a.id === id ? { ...a, read: true } : a)) }))
  }, [])

  const reload = useCallback(() => setReloads((n) => n + 1), [])

  return { ...feed, area, locate, resetArea: () => setArea(DEFAULT_AREA), markRead, reload }
}
