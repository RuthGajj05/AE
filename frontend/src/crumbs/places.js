// Everything the crumbs app loads or saves goes through this file: Google Places, the sample places and food
// types, pick events, the business report, and (later) review scores from the backend. See API.md → "crumbs map".
import { accessToken } from './auth.js'
import { buildBusinessReport } from './businessReport.js'
import alertData from './data/alerts.json'
import businessData from './data/business.json'
import cuisineData from './data/cuisines.json'
import mock from './data/mock-places.json'
import { AMBIANCE } from './metrics.js'

// Browser key from .env.local (git-ignored). Missing → the app uses the sample places on a free fallback map.
export const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''

// Backend base URL. VITE_API_URL (e.g. http://localhost:8000) talks to the backend directly; empty → relative /api,
// which the Vite dev server proxies to the backend on the machine running it. Through a tunnel that proxy answers 403
// (sample data) unless the dev server runs with SHARE_API=1; see vite.config.js. Either way, paths below start after
// /api.
const API_ROOT = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '').replace(/\/api$/, '')
export const API_BASE = `${API_ROOT}/api`

/** The signed-in owner's token for business endpoints; nothing when signed out. */
async function authHeaders() {
  const token = await accessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** GET a backend endpoint as JSON, or null when the backend is down, slow or errors (callers fall back to samples). */
async function apiGet(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers: await authHeaders(), signal: AbortSignal.timeout(4000) })
    return res.ok ? await res.json() : null
  } catch {
    return null
  }
}

/** POST JSON and wait for the answer, or null when the backend is down, slow or errors. */
async function apiPostJson(path, body, timeoutMs = 10000) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    })
    return res.ok ? await res.json() : null
  } catch {
    return null
  }
}

/** POST JSON and forget: a failed send never blocks the app. */
function apiPost(path, body) {
  fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(4000),
  }).catch(() => {})
}

export const CAPITOL_HILL = { lat: 47.619, lng: -122.321 }

const PRICE = { FREE: 'Free', INEXPENSIVE: '$', MODERATE: '$$', EXPENSIVE: '$$$', VERY_EXPENSIVE: '$$$$' }

/** "$$" for Google's price enum, or null when unknown. */
export const formatPrice = (level) => PRICE[level] ?? null

// "1525 10th Ave, Seattle, WA 98122, USA" → "1525 10th Ave, Seattle"
const shortAddress = (address) => (address ? address.split(', ').slice(0, 2).join(', ') : '')

let nearby = null

/**
 * Restaurants and cafes around Capitol Hill from Places API (New) Nearby Search.
 * `placesLib` is google.maps.places (from useMapsLibrary('places')). Cached so re-renders don't re-bill.
 */
export function searchNearbyPlaces(placesLib) {
  nearby ??= placesLib.Place.searchNearby({
    fields: ['id', 'displayName', 'primaryTypeDisplayName', 'priceLevel', 'rating', 'userRatingCount', 'formattedAddress', 'location'],
    locationRestriction: { center: CAPITOL_HILL, radius: 800 },
    includedTypes: ['restaurant', 'cafe'],
    maxResultCount: 20,
  })
    .then(({ places }) =>
      places
        .filter((p) => p.location)
        .map((p) => ({
          id: p.id,
          name: p.displayName || 'Unnamed spot',
          cuisine: p.primaryTypeDisplayName || 'Restaurant',
          priceLevel: p.priceLevel ?? null,
          rating: p.rating ?? null,
          ratingCount: p.userRatingCount ?? null,
          address: shortAddress(p.formattedAddress),
          lat: p.location.lat(),
          lng: p.location.lng(),
        })),
    )
    .catch((err) => {
      nearby = null
      throw err
    })
  return nearby
}

/** The 10 sample Capitol Hill spots, same shape as searchNearbyPlaces. */
export const getMockPlaces = () => mock.places

/** The food types for the chips: [{ id, label }]. */
export const CUISINES = cuisineData.cuisines.map(({ id, label }) => ({ id, label }))

// Words owners use for crumbs' food types ("Sushi bar", "Taqueria") → the food type; same rules as the backend's
// cuisines.match. Anything else (a bakery, a cafe) is still a business, just without crumbs' review scoring.
const FOOD_WORDS = { pizzeria: 'pizza', taqueria: 'tacos', taco: 'tacos', steakhouse: 'steak' }
export function matchCuisine(text) {
  const words = String(text ?? '').toLowerCase().split(/[^a-z0-9]+/)
  for (const word of words) {
    if (CUISINES.some((c) => c.id === word)) return word
    if (FOOD_WORDS[word]) return FOOD_WORDS[word]
  }
  return null
}

// Demo "you are here": the middle of Capitol Hill. Walks and distances are measured from it.
export const USER_LOCATION = CAPITOL_HILL

/** Walking estimate along the street grid (Capitol Hill is a N–S grid): { miles, minutes } at 3 mph. */
export function walkFromUser(spot) {
  const milesPerDegLat = 69
  const milesPerDegLng = 69 * Math.cos((USER_LOCATION.lat * Math.PI) / 180)
  const miles = Math.abs(spot.lat - USER_LOCATION.lat) * milesPerDegLat + Math.abs(spot.lng - USER_LOCATION.lng) * milesPerDegLng
  return { miles: Math.max(0.1, Math.round(miles * 10) / 10), minutes: Math.max(1, Math.round(miles * 20)) }
}

/** Walking path drawn on the map: along the user's street, then up or down the spot's avenue. [{ lat, lng }] */
export const walkPath = (spot) => [USER_LOCATION, { lat: USER_LOCATION.lat, lng: spot.lng }, { lat: spot.lat, lng: spot.lng }]

// Average of the 0–100 scores Claude could give; null scores (no review mentioned it) are left out.
const average = (values) => {
  const known = values.filter((v) => v != null)
  return known.length ? Math.round(known.reduce((sum, v) => sum + v, 0) / known.length) : null
}

/**
 * The backend's GET /api/spots → this app's compare shape (backend/API.md): up to 4 spots that have at least one
 * score, the crumbs pick first, then best overall. Food-type labels and attributes come from the local file, which
 * matches the backend's /api/cuisines.
 */
function fromBackend(payload) {
  const meta = cuisineData.cuisines.find((c) => c.id === payload?.cuisine)
  const scored = (payload?.spots ?? []).filter((s) => Object.values(s.scores ?? {}).some((v) => v != null))
  if (!meta || !scored.length) return null
  const isSample = payload.source === 'demo'
  // Demo fixtures keep the sample file's A–D order; live results lead with the pick, then best overall.
  const ranked = isSample
    ? scored
    : [...scored].sort((a, b) => Number(b.pick) - Number(a.pick) || (average(Object.values(b.scores)) ?? 0) - (average(Object.values(a.scores)) ?? 0))
  return { ...meta, spots: ranked.slice(0, 4), isSample }
}

/**
 * One food type's compare data: attributes (plus Ambiance on every food type), 4 spots, and the crumbs pick. From the
 * backend's review scores when it answers, otherwise the bundled sample data. Spots get letters A–D in order, an
 * `overall` average of the 0–100 scores, and a walk from the user. `demo: true` asks the backend for its fixtures.
 */
export async function getCuisine(id, { demo = false } = {}) {
  const query = new URLSearchParams({ cuisine: id, lat: CAPITOL_HILL.lat, lng: CAPITOL_HILL.lng, radiusMi: 1, ...(demo && { demo: 'true' }) })
  const live = fromBackend(await apiGet(`/spots?${query}`))
  const cuisine = live ?? { ...cuisineData.cuisines.find((c) => c.id === id), isSample: true }
  if (!cuisine.spots) throw new Error(`No sample data for "${id}".`)
  const spots = cuisine.spots.map((s, i) => {
    const walk = walkFromUser(s)
    return { ...s, letter: 'ABCD'[i], overall: average(Object.values(s.scores)), walk, distanceMi: walk.miles }
  })
  return {
    ...cuisine,
    attributes: [...cuisine.attributes, AMBIANCE],
    spots,
    reviewsRead: spots.reduce((sum, s) => sum + s.reviewCount, 0),
  }
}

/** Google Maps walking directions to a spot. */
export const directionsUrl = (spot) =>
  `https://www.google.com/maps/dir/?api=1&destination=${spot.lat},${spot.lng}&travelmode=walking`

// Pick events are sent to the backend (POST /api/picks, anonymous) and also kept in this browser (localStorage) for
// the sample You tab; saved spots stay local. Storage can be missing (private mode), so every read and write is wrapped.
const PICKS_KEY = 'crumbs.picks'
const SAVED_KEY = 'crumbs.saved'

function readList(key) {
  try {
    const list = JSON.parse(localStorage.getItem(key) ?? '[]')
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

function writeList(key, list) {
  try {
    localStorage.setItem(key, JSON.stringify(list))
  } catch {
    // Storage full or blocked: the demo keeps working, the event just isn't kept.
  }
}

/** Anonymous pick: which spot a user chose after comparing. No user info is stored. */
export function recordPick({ cuisine, chosenSpotId, comparedSpotIds }) {
  apiPost('/picks', { cuisine, chosenSpotId, comparedSpotIds })
  writeList(PICKS_KEY, [...readList(PICKS_KEY), { cuisine, chosenSpotId, comparedSpotIds, timestamp: new Date().toISOString() }])
}

export const readPicks = () => readList(PICKS_KEY)

export const isSaved = (spotId) => readList(SAVED_KEY).includes(spotId)

const SAVED_SPOTS_KEY = 'crumbs.savedSpots'

/**
 * Toggles a saved spot; returns whether it's saved now. `snapshot` ({ id, cuisine, name, price, bestAt, reason, lat,
 * lng }) is what the Saved tab shows, since a backend spot may not be in the sample file.
 */
export function toggleSaved(spotId, snapshot) {
  const saved = readList(SAVED_KEY)
  const next = saved.includes(spotId) ? saved.filter((id) => id !== spotId) : [...saved, spotId]
  writeList(SAVED_KEY, next)
  if (snapshot && next.includes(spotId)) {
    writeList(SAVED_SPOTS_KEY, [...readList(SAVED_SPOTS_KEY).filter((s) => s?.id !== spotId), snapshot])
  }
  return next.includes(spotId)
}

export const removeSaved = (spotId) => writeList(SAVED_KEY, readList(SAVED_KEY).filter((id) => id !== spotId))

function sampleSnapshot(spotId) {
  for (const c of cuisineData.cuisines) {
    const s = c.spots.find((spot) => spot.id === spotId)
    if (s) return { id: s.id, cuisine: c.id, name: s.name, price: s.price, bestAt: s.bestAt, reason: s.reason, lat: s.lat, lng: s.lng }
  }
  return null
}

/** Saved spots for the Saved tab, newest first, each with a walk from the user. */
export function getSavedSpots() {
  const snapshots = readList(SAVED_SPOTS_KEY)
  return [...readList(SAVED_KEY)]
    .reverse()
    .map((id) => snapshots.find((s) => s?.id === id) ?? sampleSnapshot(id))
    .filter(Boolean)
    .map((s) => ({ ...s, walk: walkFromUser(s) }))
}

/** The backend's insights breakdown → the `you` scores this app's business report reads. */
function youFromBreakdown(you, breakdown) {
  const row = (id) => breakdown.find((r) => r.attribute === id)?.you
  const scores = Object.fromEntries(Object.keys(you.scores).map((id) => [id, row(id) ?? you.scores[id]]))
  return { ...you, scores, waitMinutes: row('wait') ?? you.waitMinutes, ambiancePct: row('ambiance') ?? you.ambiancePct }
}

/**
 * The business side (You tab): picks won and lost, why rivals won, and the breakdown vs the area. From the backend's
 * rivals + insights for the sample business (its picks table already includes this browser's taps), compared against
 * the backend's sample spots; otherwise built from the bundled sample data plus this browser's pick events.
 */
export async function getBusinessReport() {
  const { id, cuisine } = businessData.you
  const [rivals, insights] = await Promise.all([apiGet(`/business/${id}/rivals?days=7`), apiGet(`/business/${id}/insights`)])
  if (rivals && insights?.breakdown?.length) {
    const data = {
      ...businessData,
      you: youFromBreakdown(businessData.you, insights.breakdown),
      picksWon: rivals.picksWon,
      picksLostTo: Object.fromEntries(rivals.rivals.map((r) => [r.spotId, r.picksWon])),
    }
    return buildBusinessReport(data, await getCuisine(cuisine, { demo: true }), [])
  }
  return buildBusinessReport(businessData, await getCuisine(cuisine), readPicks())
}

/**
 * Freshness / Value / Service from Claude's review analysis (contract in API.md). Until the backend answers, every
 * score is null and the card shows "—".
 */
export async function getPlaceScores(placeId) {
  const scores = placeId ? await apiGet(`/places/${encodeURIComponent(placeId)}/scores`) : null
  return { freshness: scores?.freshness ?? null, value: scores?.value ?? null, service: scores?.service ?? null }
}

// ---------- Alerts ----------

const ALERTS_READ_KEY = 'crumbs.alertsRead'

/** The sample feed, shifted so the newest alert is always 12 minutes old in the demo. */
function sampleAlerts(audience) {
  const newest = Math.max(...alertData.alerts.map((a) => Date.parse(a.createdAt)))
  const shift = Date.now() - 12 * 60 * 1000 - newest
  return alertData.alerts
    .filter((a) => audience === 'business' || a.audience === 'consumer')
    .map((a) => ({ ...a, createdAt: new Date(Date.parse(a.createdAt) + shift).toISOString() }))
}

/** One GET /api/alerts list, or null when the backend is down or errors. */
async function fetchAlerts(params) {
  const payload = await apiGet(`/alerts?${new URLSearchParams(params)}`)
  return Array.isArray(payload) ? payload : Array.isArray(payload?.alerts) ? payload.alerts : null
}

/**
 * Alerts near a point, newest first (backend/API.md → Alerts). Everyone gets the consumer feed; business accounts
 * also get their owner alerts (the sample shop's id until onboarding registers with the backend). A list the backend
 * has nothing for yet is asked again with `demo=true`; no backend → the sample file. Read flags merge with the ones
 * kept in this browser.
 */
export async function getAlerts({ lat, lng, audience, businessId }) {
  const requests = [{ audience: 'consumer', lat, lng, radiusMi: 1 }]
  if (audience === 'business') requests.push({ audience: 'business', businessId: businessId ?? businessData.you.id })
  const lists = await Promise.all(
    requests.map(async (params) => {
      const list = await fetchAlerts(params)
      return list && !list.length ? fetchAlerts({ ...params, demo: 'true' }) : list
    }),
  )
  const live = lists[0] === null ? null : lists.flatMap((l) => l ?? [])
  const read = new Set(readList(ALERTS_READ_KEY))
  const alerts = (live ?? sampleAlerts(audience))
    .map((a) => ({ ...a, read: Boolean(a.read) || read.has(a.id) }))
    .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
  return { alerts, isSample: !live || live.some((a) => a.demo) }
}

/** POST /api/alerts/{id}/read, and remember it here so the sample feed stays read too. */
export function markAlertRead(id) {
  apiPost(`/alerts/${encodeURIComponent(id)}/read`, {})
  const read = readList(ALERTS_READ_KEY)
  if (!read.includes(id)) writeList(ALERTS_READ_KEY, [...read, id])
}

// ---------- the business's own report (Ruth's advisor, via the backend) ----------

/**
 * POST /api/business/onboard: registers the spot with the backend, which researches nearby competitors and writes
 * a tailored report in the background (about a minute). { businessId, reportQueued } or null when the backend is
 * down, in which case the account stays local and the app keeps showing sample data.
 */
export function onboardBusiness({ name, address, type }, { advisorReport = true } = {}) {
  return apiPostJson('/business/onboard', { name, address, businessType: type, advisorReport })
}

/**
 * GET /api/business/{id}/report: { status: none | running | complete | failed, error, summary, report }, or null.
 * `demo` asks for the saved example report.
 */
export function getAdvisorReport(businessId, { demo = false } = {}) {
  return apiGet(`/business/${encodeURIComponent(businessId)}/report${demo ? '?demo=true' : ''}`)
}

/** POST /api/business/{id}/report: start a fresh report. { status: 'running' } or null. */
export function refreshAdvisorReport(businessId) {
  return apiPostJson(`/business/${encodeURIComponent(businessId)}/report`, {})
}

/** GET /api/me: { user, business } for the signed-in owner (business: their spot or null), or null. */
export function getMe() {
  return apiGet('/me')
}


// ---------- sales data (optional: CSV, Square or Toast) ----------

/** A business call whose error message the owner needs to see: { ok, data } or { ok: false, error }. */
async function apiSend(method, path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(30000),
    })
    const data = await res.json().catch(() => null)
    return res.ok ? { ok: true, data } : { ok: false, error: data?.error ?? `The server answered ${res.status}.` }
  } catch {
    return { ok: false, error: "We couldn't reach the crumbs backend. Is it running?" }
  }
}

const salesPath = (businessId) => `/business/${encodeURIComponent(businessId)}/sales`

/** { connected, source, label, connectedAt, … } — never credentials. */
export const getSales = (businessId) => apiSend('GET', salesPath(businessId))
export const disconnectSales = (businessId) => apiSend('DELETE', salesPath(businessId))

/** Upload a sales export (Square "Items" CSV format). Starts a fresh report unless refreshReport is false. */
export async function connectCsv(businessId, file, { refreshReport = true } = {}) {
  if (file.size > 5 * 1024 * 1024) return { ok: false, error: 'That file is over 5 MB. Export a shorter period, like the last 8 weeks.' }
  const content = await file.text()
  return apiSend('POST', `${salesPath(businessId)}/csv?refreshReport=${refreshReport}`, { filename: file.name, content })
}

export const connectSquare = (businessId, { accessToken, environment }, { refreshReport = true } = {}) =>
  apiSend('POST', `${salesPath(businessId)}/square?refreshReport=${refreshReport}`, { accessToken, environment })

export const connectToast = (businessId, { clientId, clientSecret, restaurantGuid }, { refreshReport = true } = {}) =>
  apiSend('POST', `${salesPath(businessId)}/toast?refreshReport=${refreshReport}`, { clientId, clientSecret, restaurantGuid })

// ---------- competitor checks and alert emails ----------

/** Run the competitor monitor now (about a minute, in the background); new changes arrive as owner alerts. */
export const checkCompetitorsNow = (businessId) =>
  apiSend('POST', `/business/${encodeURIComponent(businessId)}/alerts/refresh?monitor=true&stock=false`)

/** { emailAlerts, ownerEmail, recentEmails: [{ subject, status, detail, createdAt }] } */
export const getAlertSettings = (businessId) => apiSend('GET', `/business/${encodeURIComponent(businessId)}/settings`)
export const setAlertEmails = (businessId, emailAlerts) =>
  apiSend('POST', `/business/${encodeURIComponent(businessId)}/settings`, { emailAlerts })
