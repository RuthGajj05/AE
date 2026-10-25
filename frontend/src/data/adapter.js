// Maps the scraper report (Ruth's format, see API.md) into the one shape the UI renders.
// Field names are matched loosely (review_count, reviewCount, reviews, ...) and anything
// missing or malformed gets a safe default, so the dashboard never crashes on bad data.
//
// Output shape:
// {
//   source: 'bundled' | 'url' | 'file',
//   reportDate: Date | null, dateOnly: boolean,
//   business:    { name, type, area, rating, reviewCount, avgPrice, waitMin },
//   summary:     string,
//   competitors: [{ id, name, address, distanceMi, distanceNote, rating, reviewCount, avgPrice, minPrice,
//                   prices: [{ item, price }], waitMin, topWeakness, complaints, praisedFor, specialties,
//                   sources, url, lat, lng }],
//   themes:      [{ id, label, count, unit: 'shops' | 'mentions', quote, quoteBy }],  // high to low
//   benchmarks:  [{ id, item, min, max, note }],
//   suggestions: [{ id, title, why, evidence, impact: 'high' | 'medium' | 'low' | null }],
//   caveats:     [string],
// }
// Unknown numbers are null and unknown strings are '' — components show "—" or hide them.

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

const texts = (v) => (Array.isArray(v) ? v.map(text).filter(Boolean) : text(v) ? [text(v)] : [])

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

const between = (n, min, max) => (n === null || n < min || n > max ? null : n)
const dollars = (s) => [...String(s).matchAll(/\$\s*(\d+(?:\.\d+)?)/g)].map((m) => Number(m[1]))

/** "~630 m (OSM)", "~0.6 mi east", "~1.5 km, Madison Valley edge" → miles. */
function miles(v) {
  const n = num(v)
  if (n === null || typeof v !== 'string') return between(n, 0, 500)
  if (/\d\s*km\b|kilomet/i.test(v)) return n * 0.621371
  if (/\d\s*m\b|\bmeters?\b|\bmetres?\b/i.test(v)) return n / 1609.34
  return between(n, 0, 500)
}

function safeUrl(v) {
  const s = text(v)
  return /^https?:\/\//i.test(s) ? s : ''
}

/** Date-only strings like "2026-10-25" are local calendar dates, not UTC midnight. */
function toDate(v) {
  if (v === undefined) return { date: null, dateOnly: false }
  const s = text(v)
  const day = s.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (day) return { date: new Date(+day[1], +day[2] - 1, +day[3]), dateOnly: true }
  const d = new Date(typeof v === 'number' && v < 1e12 ? v * 1000 : v)
  return Number.isNaN(d.getTime()) ? { date: null, dateOnly: false } : { date: d, dateOnly: false }
}

function list(v) {
  if (Array.isArray(v)) return v
  // Some scrapers send maps, e.g. { "Long waits": 57 } or { "a": {...}, "b": {...} }.
  if (isObject(v)) return Object.entries(v).map(([k, val]) => (isObject(val) ? { name: k, ...val } : { name: k, value: val }))
  return []
}

const capitalize = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)

/** Drops a trailing source note and wrapping quotes: "'Even pricier now' (TripAdvisor)" → "Even pricier now". */
function cleanQuote(s) {
  const t = s.replace(/\s*\([^)]*\)\s*$/, '').trim()
  const wrapped = t.match(/^['"‘“](.*)['"’”]$/)
  return capitalize((wrapped ? wrapped[1] : t).trim())
}

/** Splits a paragraph after its first sentence, skipping abbreviations like "Mt." or "St.". */
function firstSentence(s) {
  for (const m of s.matchAll(/[.!?](?=\s+["“'‘]?[A-Z0-9$])/g)) {
    const word = s.slice(0, m.index).split(/\s+/).pop()
    if (/^(Mt|St|Ave|Dr|Blvd|Rd|vs|No|Inc|Co|Jr|Sr|Mr|Mrs|Ms|e\.g|i\.e|approx)$/i.test(word)) continue
    return [s.slice(0, m.index + 1).trim(), s.slice(m.index + 1).trim()]
  }
  return [s.trim(), '']
}

// Complaint themes, matched against the free-text complaints in the report.
// Each theme counts once per shop. If the report sends its own themes, those win.
const THEME_RULES = [
  ['price', 'Too expensive', /expensive|overpriced|pricier|pricey|costly|prices? rose|price hike/i],
  ['service', 'Unfriendly service', /service|friendly|rude|staff|attitude|incident|ignored/i],
  ['hours', 'Short hours or closed days', /\bclosed\b|open only|\bhours\b|until \d|closes (at|by|early)/i],
  ['quality', 'Quality slips', /\bdry\b|hollow|stale|bland|burnt|soggy|quality|inconsistent/i],
  ['wait', 'Long waits', /\bwaits?\b|takes a while|\bslow\b|long lines?/i],
  ['sellout', 'Sells out early', /sells? out|sold out|runs? out/i],
  ['portions', 'Small portions', /smallish|small portion|portion|\bsmall\b/i],
  ['seating', 'Nowhere to sit', /\bseat(s|ing)?\b/i],
  ['options', 'Limited options', /does not slice|won't slice|card only|cash only|limited menu|selection/i],
]

const themesIn = (complaint) => THEME_RULES.filter(([, , re]) => re.test(complaint))

function parsePricePoint(raw) {
  const s = text(raw)
  if (!s) return null
  const [price] = dollars(s)
  if (price === undefined) return null
  const colon = s.indexOf(':')
  const item = (colon > 0 ? s.slice(0, colon) : s.slice(0, s.indexOf('$')))
    .replace(/\([^)]*\)/g, '')
    .trim()
  return { item: item || 'Item', price }
}

function toBusiness(raw, root) {
  // Ruth's report has the business as a plain name, with type and location beside it.
  const b = isObject(raw) ? raw : {}
  return {
    name: text(typeof raw === 'string' ? raw : pick(b, 'name', 'businessName', 'title')) || 'Your business',
    type: capitalize(text(pick(b, 'type', 'category', 'cuisine', 'kind') ?? pick(root, 'type', 'category'))),
    area: text(pick(b, 'area', 'neighborhood', 'location', 'city', 'address') ?? pick(root, 'location', 'area', 'neighborhood')),
    rating: between(num(pick(b, 'rating', 'stars', 'avgRating', 'googleRating')), 0, 5),
    reviewCount: between(num(pick(b, 'reviewCount', 'reviews', 'numReviews', 'totalReviews')), 0, 1e7),
    avgPrice: between(num(pick(b, 'avgPrice', 'averagePrice', 'price', 'itemPrice')), 0, 1000),
    waitMin: between(num(pick(b, 'waitMin', 'avgWaitMinutes', 'wait', 'waitTime', 'avgWait')), 0, 600),
  }
}

function toCompetitor(raw, i) {
  if (!isObject(raw)) return null
  const name = text(pick(raw, 'name', 'businessName', 'title'))
  if (!name) return null
  const distanceRaw = pick(raw, 'distanceMi', 'distance', 'distanceNote', 'distanceMiles', 'dist', 'miles')
  const prices = texts(pick(raw, 'pricePoints', 'prices', 'menuPrices')).map(parsePricePoint).filter(Boolean)
  const complaints = texts(pick(raw, 'complaints', 'customerComplaints', 'weaknesses'))
  const firstTheme = complaints.map(themesIn).find((t) => t.length)?.[0]
  const explicitWeakness = text(pick(raw, 'topWeakness', 'weakness', 'topComplaint', 'mainComplaint'))
  const lat = between(num(pick(raw, 'lat', 'latitude')), -90, 90)
  const lng = between(num(pick(raw, 'lng', 'lon', 'long', 'longitude')), -180, 180)

  return {
    id: `c${i}`,
    name,
    address: text(pick(raw, 'address', 'street')),
    distanceMi: miles(distanceRaw),
    distanceNote: typeof distanceRaw === 'string' ? distanceRaw : '',
    rating: between(num(pick(raw, 'rating', 'stars', 'avgRating', 'googleRating')), 0, 5),
    reviewCount: between(num(pick(raw, 'reviewCount', 'reviews', 'numReviews', 'totalReviews', 'userRatingsTotal')), 0, 1e7),
    avgPrice: between(num(pick(raw, 'avgPrice', 'averagePrice', 'price', 'itemPrice', 'priceRange')), 0, 1000),
    minPrice: prices.length ? Math.min(...prices.map((p) => p.price)) : null,
    prices,
    waitMin: between(num(pick(raw, 'waitMin', 'wait', 'waitTime', 'typicalWait', 'avgWait')), 0, 600),
    topWeakness: explicitWeakness || firstTheme?.[1] || (complaints[0] ? cleanQuote(complaints[0]) : ''),
    complaints: complaints.map((c) => c.trim()),
    praisedFor: texts(pick(raw, 'praisedFor', 'strengths', 'praise', 'pros')),
    specialties: texts(pick(raw, 'specialties', 'knownFor', 'menuHighlights')),
    sources: texts(pick(raw, 'sources', 'sourceUrls', 'links')).map(safeUrl).filter(Boolean),
    url: safeUrl(pick(raw, 'website', 'url', 'link', 'mapsUrl')),
    lat: lat !== null && lng !== null ? lat : null,
    lng: lat !== null && lng !== null ? lng : null,
  }
}

function toTheme(raw, i) {
  const label = typeof raw === 'string' ? raw.trim() : text(pick(raw, 'theme', 'label', 'name', 'complaint', 'topic'))
  if (!label) return null
  return {
    id: `t${i}`,
    label,
    count: Math.max(0, Math.round(num(pick(raw, 'mentions', 'count', 'value', 'total', 'shops')) ?? 0)),
    unit: pick(raw, 'shops') !== undefined ? 'shops' : 'mentions',
    quote: text(pick(raw, 'quote', 'example', 'sample', 'snippet', 'review')),
    quoteBy: text(pick(raw, 'quoteBy', 'business', 'source')),
  }
}

/** Groups each competitor's free-text complaints into themes, counted by number of shops. */
function themesFromCompetitors(competitors) {
  const found = new Map()
  for (const c of competitors) {
    const seen = new Set()
    for (const complaint of c.complaints) {
      for (const [key, label, re] of themesIn(complaint)) {
        // Quote the clause that matched ("sells out quickly"), not the whole "a; b; c" note.
        const clause = cleanQuote(complaint.split(/;\s*/).find((part) => re.test(part)) ?? complaint)
        const t = found.get(key) ?? { id: key, label, count: 0, unit: 'shops', quote: '', quoteBy: '' }
        if (!seen.has(key)) t.count += 1
        // Nearest shops come first; keep their quote unless it's too short or long to read well.
        const readable = (q) => q.length >= 20 && q.length <= 60
        if (!t.quote || (!readable(t.quote) && readable(clause))) Object.assign(t, { quote: clause, quoteBy: c.name })
        seen.add(key)
        found.set(key, t)
      }
    }
  }
  return [...found.values()]
}

/** "Plain butter croissant: $3.50–$6.25 (3 shops: Bakery Nouveau $3.50, ...)" → item, min, max, note. */
function toBenchmark(raw, i) {
  const s = text(isObject(raw) ? pick(raw, 'text', 'benchmark') : raw)
  const item = isObject(raw) ? text(pick(raw, 'item', 'name')) : ''
  if (isObject(raw) && item) {
    const min = num(pick(raw, 'min', 'low'))
    const max = num(pick(raw, 'max', 'high')) ?? min
    return min === null ? null : { id: `b${i}`, item, min, max, note: text(pick(raw, 'note', 'detail')) }
  }
  const colon = s.indexOf(':')
  if (colon < 1) return null
  const rest = s.slice(colon + 1)
  const paren = rest.indexOf('(')
  const values = dollars(paren >= 0 ? rest.slice(0, paren) : rest)
  if (!values.length) return null
  return {
    id: `b${i}`,
    item: s.slice(0, colon).trim(),
    min: Math.min(...values),
    max: Math.max(...values),
    note: paren >= 0 ? rest.slice(paren + 1).replace(/\)\s*$/, '').trim() : '',
  }
}

function impact(v) {
  const s = normKey(text(v))
  if (!s) return null
  if (['high', 'h', 'major', 'big', '3'].includes(s)) return 'high'
  if (['low', 'l', 'minor', 'small', '1'].includes(s)) return 'low'
  return 'medium'
}

function toSuggestion(raw, i) {
  if (typeof raw === 'string') return raw.trim() ? { id: `s${i}`, title: raw.trim(), why: '', evidence: '', impact: null } : null
  let title = text(pick(raw, 'title', 'headline', 'name'))
  let why = text(pick(raw, 'why', 'detail', 'details', 'description', 'reason', 'body'))
  const recommendation = text(pick(raw, 'recommendation', 'suggestion', 'tip'))
  if (!title && recommendation) {
    // Ruth's insights are one paragraph; the first sentence becomes the headline.
    ;[title, why] = firstSentence(recommendation)
  }
  if (!title) return null
  return { id: `s${i}`, title, why, evidence: text(pick(raw, 'evidence', 'because')), impact: impact(pick(raw, 'impact', 'priority', 'level')) }
}

const money = (usd) => (typeof usd === 'number' && usd > 0 ? `~$${Math.round(usd).toLocaleString()}/mo` : '')

/** Same-named items priced at 2+ shops → "Item: $min–$max (N shops)", the benchmark pattern the range chart reads. */
function benchmarksFrom(competitors) {
  const byItem = new Map()
  for (const c of competitors) {
    for (const point of texts(pick(c, 'price_points', 'pricePoints'))) {
      const [label, rest] = point.split(/:(.*)/s)
      const price = dollars(rest ?? '')[0]
      if (!rest || price === undefined) continue
      const key = label.trim().toLowerCase()
      const entry = byItem.get(key) ?? { label: capitalize(label.trim()), prices: new Map() }
      if (!entry.prices.has(c.name)) entry.prices.set(c.name, price)
      byItem.set(key, entry)
    }
  }
  return [...byItem.values()]
    .filter((e) => e.prices.size >= 2)
    .map((e) => {
      const prices = [...e.prices.values()]
      const fmt = (n) => `$${n.toFixed(2).replace(/\.00$/, '')}`
      return `${e.label}: ${fmt(Math.min(...prices))}–${fmt(Math.max(...prices))} (${e.prices.size} shops)`
    })
}

/**
 * Ruth's advisor report ({ advice, competitors: { competitors }, ... }, or the backend's /business/{id}/report view
 * around it) → the scraper-report fields below: the snapshot is the summary, recommendations are the suggestions.
 */
function fromAdvisorReport(root) {
  const advice = pick(root, 'advice')
  const research = pick(root, 'competitors')
  if (!isObject(advice) || !isObject(research)) return root
  const competitors = list(pick(research, 'competitors'))
  return {
    ...root,
    marketSummary: pick(advice, 'snapshot'),
    competitors,
    priceBenchmarks: benchmarksFrom(competitors),
    insights: list(pick(advice, 'recommendations')).map((r) => ({
      title: [text(pick(r, 'title')), money(pick(r, 'est_monthly_impact_usd'))].filter(Boolean).join(' · '),
      why: text(pick(r, 'action')),
      evidence: [pick(r, 'evidence_from_your_business'), pick(r, 'evidence_from_market'), pick(r, 'impact_math')]
        .map(text)
        .filter((t) => t && t !== 'none')
        .join(' '),
    })),
    gapsAndCaveats: [...texts(pick(research, 'gaps_and_caveats')), ...texts(pick(advice, 'caveats'))],
  }
}

export function toDashboard(raw, { source = 'url' } = {}) {
  // A bare array is a list of competitors; a backend wrapper ({ profile, report }) is unwrapped.
  let root = Array.isArray(raw) ? { competitors: raw } : isObject(raw) ? raw : {}
  const wrapped = pick(root, 'report')
  if (isObject(wrapped)) {
    // The profile holds the owner's own numbers; Ruth's report only names the business, so the profile wins and
    // borrows that name when it has none.
    const profile = pick(root, 'profile', 'business')
    const reported = pick(wrapped, 'business')
    let business = profile ?? reported
    if (isObject(profile) && pick(profile, 'name', 'businessName', 'title') === undefined && typeof reported === 'string') {
      business = { ...profile, name: reported }
    }
    root = { ...wrapped, business }
  }
  root = fromAdvisorReport(root)

  const competitors = list(pick(root, 'competitors', 'nearby', 'nearbyBusinesses', 'businesses', 'results', 'places'))
    .map(toCompetitor)
    .filter(Boolean)
    .sort((a, b) => (a.distanceMi ?? Infinity) - (b.distanceMi ?? Infinity))

  const rawThemes = list(pick(root, 'complaintThemes', 'reviewThemes', 'themes', 'painPoints'))
  const themes = (rawThemes.length ? rawThemes.map(toTheme).filter(Boolean) : themesFromCompetitors(competitors)).sort(
    (a, b) => b.count - a.count,
  )

  const { date, dateOnly } = toDate(pick(root, 'date', 'generatedAt', 'scrapedAt', 'updatedAt', 'timestamp', 'createdAt'))

  return {
    source,
    reportDate: date,
    dateOnly,
    business: toBusiness(pick(root, 'business', 'you', 'self', 'target', 'myBusiness', 'restaurant', 'shop'), root),
    summary: text(pick(root, 'marketSummary', 'summary', 'overview')),
    competitors,
    themes,
    benchmarks: list(pick(root, 'priceBenchmarks', 'benchmarks', 'prices')).map(toBenchmark).filter(Boolean),
    suggestions: list(pick(root, 'insights', 'suggestions', 'recommendations', 'tips', 'actions')).map(toSuggestion).filter(Boolean),
    caveats: texts(pick(root, 'gapsAndCaveats', 'caveats', 'limitations', 'gaps')),
  }
}

/** Averages over competitors that have a value; null when none do. */
export function average(items, key) {
  const values = items.map((c) => c[key]).filter((v) => v !== null)
  return values.length ? values.reduce((s, v) => s + v, 0) / values.length : null
}
