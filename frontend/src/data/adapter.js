// Maps whatever JSON the scraper produces into the one shape the UI renders.
// Field names are matched loosely (avgPrice, avg_price, price, ...) and anything
// missing or malformed gets a safe default, so the dashboard never crashes on bad data.
//
// Output shape:
// {
//   source: 'sample' | 'live' | 'file',
//   updatedAt: Date | null,
//   business:    { name, type, area, rating, reviewCount, avgPrice, waitMin },
//   competitors: [{ id, name, distanceMi, rating, reviewCount, avgPrice, waitMin, topWeakness, url }],
//   themes:      [{ id, label, mentions, quote }],   // sorted by mentions, high to low
//   suggestions: [{ id, title, why, impact: 'high' | 'medium' | 'low' }],
// }
// Unknown numbers are null and unknown strings are '' — components show "—" for them.

const normKey = (k) => String(k).toLowerCase().replace(/[^a-z0-9]/g, '')
const isObject = (v) => typeof v === 'object' && v !== null && !Array.isArray(v)

/** First value present under any of the given names, ignoring case, dashes and underscores. */
function pick(obj, ...names) {
  if (!isObject(obj)) return undefined
  const lookup = new Map(Object.keys(obj).map((k) => [normKey(k), obj[k]]))
  for (const name of names) {
    const v = lookup.get(normKey(name))
    if (v !== undefined && v !== null && v !== '') return v
  }
  return undefined
}

function text(v) {
  if (typeof v === 'string') return v.trim()
  if (typeof v === 'number' && Number.isFinite(v)) return String(v)
  return ''
}

/** Reads numbers from scraped strings like "$5.10", "1,204", "4.5 stars" or "15–20 min" (uses the midpoint). */
function num(v) {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v !== 'string') return null
  const s = v.replace(/[$,]/g, '')
  const range = s.match(/(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)/)
  if (range) return (Number(range[1]) + Number(range[2])) / 2
  const n = parseFloat(s.replace(/^[^\d.-]+/, ''))
  return Number.isFinite(n) ? n : null
}

function between(n, min, max) {
  return n === null || n < min || n > max ? null : n
}

function miles(v) {
  const n = num(v)
  if (n === null || typeof v !== 'string') return between(n, 0, 500)
  if (/\bkm\b|kilomet/i.test(v)) return n * 0.621371
  if (/\d\s*m\b|\bmeters?\b|\bmetres?\b/i.test(v)) return n / 1609.34
  return between(n, 0, 500)
}

function safeUrl(v) {
  const s = text(v)
  return /^https?:\/\//i.test(s) ? s : ''
}

function date(v) {
  if (v === undefined) return null
  const d = new Date(typeof v === 'number' && v < 1e12 ? v * 1000 : v)
  return Number.isNaN(d.getTime()) ? null : d
}

function list(v) {
  if (Array.isArray(v)) return v
  // Some scrapers send maps, e.g. { "Long waits": 57 } or { "a": {...}, "b": {...} }.
  if (isObject(v)) return Object.entries(v).map(([k, val]) => (isObject(val) ? { name: k, ...val } : { name: k, value: val }))
  return []
}

function topOf(complaints) {
  const entries = list(complaints)
    .map((c) => ({ label: text(pick(c, 'theme', 'label', 'name')), n: num(pick(c, 'mentions', 'count', 'value')) ?? 0 }))
    .filter((c) => c.label)
    .sort((a, b) => b.n - a.n)
  return entries[0]?.label ?? ''
}

function toBusiness(raw) {
  const b = isObject(raw) ? raw : {}
  return {
    name: text(pick(b, 'name', 'businessName', 'title')) || 'Your business',
    type: text(pick(b, 'type', 'category', 'cuisine', 'kind')),
    area: text(pick(b, 'area', 'neighborhood', 'location', 'city', 'address')),
    rating: between(num(pick(b, 'rating', 'stars', 'avgRating', 'googleRating')), 0, 5),
    reviewCount: between(num(pick(b, 'reviewCount', 'reviews', 'numReviews', 'totalReviews', 'userRatingsTotal')), 0, 1e7),
    avgPrice: between(num(pick(b, 'avgPrice', 'averagePrice', 'price', 'itemPrice', 'avgItemPrice')), 0, 1000),
    waitMin: between(num(pick(b, 'waitMin', 'wait', 'waitTime', 'avgWait', 'waitMinutes')), 0, 600),
  }
}

function toCompetitor(raw, i) {
  if (!isObject(raw)) return null
  const name = text(pick(raw, 'name', 'businessName', 'title'))
  if (!name) return null
  return {
    id: `c${i}`,
    name,
    distanceMi: miles(pick(raw, 'distanceMi', 'distance', 'distanceMiles', 'dist', 'miles')),
    rating: between(num(pick(raw, 'rating', 'stars', 'avgRating', 'googleRating')), 0, 5),
    reviewCount: between(num(pick(raw, 'reviewCount', 'reviews', 'numReviews', 'totalReviews', 'userRatingsTotal')), 0, 1e7),
    avgPrice: between(num(pick(raw, 'avgPrice', 'averagePrice', 'price', 'itemPrice', 'avgItemPrice')), 0, 1000),
    waitMin: between(num(pick(raw, 'waitMin', 'wait', 'waitTime', 'avgWait', 'waitMinutes')), 0, 600),
    topWeakness:
      text(pick(raw, 'topWeakness', 'weakness', 'topComplaint', 'mainComplaint', 'biggestComplaint')) ||
      topOf(pick(raw, 'complaints', 'themes', 'reviewThemes')),
    url: safeUrl(pick(raw, 'url', 'website', 'link', 'mapsUrl')),
  }
}

function toTheme(raw, i) {
  if (typeof raw === 'string') return raw.trim() ? { id: `t${i}`, label: raw.trim(), mentions: 0, quote: '' } : null
  const label = text(pick(raw, 'theme', 'label', 'name', 'complaint', 'topic'))
  if (!label) return null
  return {
    id: `t${i}`,
    label,
    mentions: Math.max(0, Math.round(num(pick(raw, 'mentions', 'count', 'value', 'total', 'n')) ?? 0)),
    quote: text(pick(raw, 'quote', 'example', 'sample', 'snippet', 'review')),
  }
}

/** Adds up per-competitor complaint counts when the scraper didn't send overall themes. */
function themesFromCompetitors(rawCompetitors) {
  const totals = new Map()
  for (const c of list(rawCompetitors)) {
    for (const t of list(pick(c, 'complaints', 'themes', 'reviewThemes'))) {
      const label = text(pick(t, 'theme', 'label', 'name'))
      if (label) totals.set(label, (totals.get(label) ?? 0) + (num(pick(t, 'mentions', 'count', 'value')) ?? 0))
    }
  }
  return [...totals].map(([theme, mentions]) => ({ theme, mentions }))
}

function impact(v) {
  const s = normKey(text(v))
  if (['high', 'h', 'major', 'big', '3'].includes(s)) return 'high'
  if (['low', 'l', 'minor', 'small', '1'].includes(s)) return 'low'
  return 'medium'
}

function toSuggestion(raw, i) {
  if (typeof raw === 'string') return raw.trim() ? { id: `s${i}`, title: raw.trim(), why: '', impact: 'medium' } : null
  const title = text(pick(raw, 'title', 'suggestion', 'name', 'headline', 'tip'))
  if (!title) return null
  return {
    id: `s${i}`,
    title,
    why: text(pick(raw, 'why', 'reason', 'evidence', 'description', 'detail', 'details', 'body')),
    impact: impact(pick(raw, 'impact', 'priority', 'level')),
  }
}

export function toDashboard(raw, { source } = {}) {
  // A bare array is treated as a list of competitors.
  const root = Array.isArray(raw) ? { competitors: raw } : isObject(raw) ? raw : {}

  const rawCompetitors = pick(root, 'competitors', 'nearby', 'nearbyBusinesses', 'businesses', 'results', 'places')
  const competitors = list(rawCompetitors)
    .map(toCompetitor)
    .filter(Boolean)
    .sort((a, b) => (a.distanceMi ?? Infinity) - (b.distanceMi ?? Infinity))

  const rawThemes = list(pick(root, 'reviewThemes', 'themes', 'complaints', 'reviewComplaints', 'painPoints'))
  const themes = (rawThemes.length ? rawThemes : themesFromCompetitors(rawCompetitors))
    .map(toTheme)
    .filter(Boolean)
    .sort((a, b) => b.mentions - a.mentions)

  const suggestions = list(pick(root, 'suggestions', 'recommendations', 'tips', 'insights', 'actions'))
    .map(toSuggestion)
    .filter(Boolean)

  const declared = text(pick(root, 'source'))
  return {
    source: source ?? (declared === 'sample' ? 'sample' : 'live'),
    updatedAt: date(pick(root, 'generatedAt', 'scrapedAt', 'updatedAt', 'timestamp', 'createdAt')),
    business: toBusiness(pick(root, 'business', 'you', 'self', 'target', 'myBusiness', 'restaurant', 'shop')),
    competitors,
    themes,
    suggestions,
  }
}

/** Averages over competitors that have a value; null when none do. */
export function average(items, key) {
  const values = items.map((c) => c[key]).filter((v) => v !== null)
  return values.length ? values.reduce((s, v) => s + v, 0) / values.length : null
}
