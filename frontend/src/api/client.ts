// Every call to the backend lives in this file. With VITE_API_URL unset (or `?mock`
// in the page URL) it answers from ./mock.ts instead; the contract is in API.md.
import { CATEGORIES, NEIGHBORHOODS, THEMES } from '../data/reference'
import type {
  Competitor,
  CompetitorsResponse,
  Impact,
  Profile,
  Recommendation,
  RecommendationsRequest,
  RecommendationsResponse,
  Theme,
} from '../types'
import * as mock from './mock'

const API_URL = (import.meta.env.VITE_API_URL ?? '').trim().replace(/\/+$/, '')
const forceMock = new URLSearchParams(window.location.search).has('mock')

export const usingMocks = !API_URL || forceMock

/** Scraping and Claude calls can be slow; give up after this long. */
const TIMEOUT_MS = 90_000

export class ApiError extends Error {}

async function request(path: string, init: RequestInit, signal?: AbortSignal): Promise<unknown> {
  const timeout = AbortSignal.timeout(TIMEOUT_MS)
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, signal: signal ? AbortSignal.any([signal, timeout]) : timeout })
  } catch (err) {
    if (signal?.aborted) throw err
    if (timeout.aborted) throw new ApiError('The server took too long to answer.')
    throw new ApiError(`Couldn't reach the server at ${API_URL}. Is the backend running?`)
  }
  const body: unknown = await res.json().catch(() => null)
  if (!res.ok) {
    const message = (body as { error?: unknown } | null)?.error
    throw new ApiError(typeof message === 'string' ? message : `Server error ${res.status}.`)
  }
  return body
}

export async function getCompetitors(profile: Profile, radiusMi: number, signal?: AbortSignal): Promise<CompetitorsResponse> {
  if (usingMocks) return mock.getCompetitors(profile, radiusMi, signal)
  const { lat, lng } = NEIGHBORHOODS[profile.neighborhood]
  const query = new URLSearchParams({
    category: profile.category,
    item: CATEGORIES[profile.category].item,
    neighborhood: profile.neighborhood,
    lat: String(lat),
    lng: String(lng),
    radiusMi: String(radiusMi),
  })
  return parseCompetitorsResponse(await request(`/api/competitors?${query}`, { method: 'GET' }, signal))
}

export async function getRecommendations(
  profile: Profile,
  competitors: Competitor[],
  signal?: AbortSignal,
): Promise<RecommendationsResponse> {
  if (usingMocks) return mock.getRecommendations(profile, competitors, signal)
  const body: RecommendationsRequest = { profile, competitors }
  const raw = await request(
    '/api/recommendations',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    signal,
  )
  return parseRecommendationsResponse(raw)
}

// Scraped data is messy. Coerce what we can, drop what we can't, and never let a
// bad field crash the dashboard.

type Json = Record<string, unknown>
const isObject = (v: unknown): v is Json => typeof v === 'object' && v !== null && !Array.isArray(v)

function num(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v.replace(/[$,%\s]/g, ''))
    return Number.isFinite(n) ? n : null
  }
  return null
}

const str = (v: unknown): string => (typeof v === 'string' ? v.trim() : '')

function parseComplaints(v: unknown): Partial<Record<Theme, number>> {
  const out: Partial<Record<Theme, number>> = {}
  if (!isObject(v)) return out
  for (const [key, count] of Object.entries(v)) {
    const n = num(count)
    if (key in THEMES && n !== null && n > 0) out[key as Theme] = Math.round(n)
  }
  return out
}

function parseCompetitor(v: unknown, index: number): Competitor | null {
  if (!isObject(v) || !str(v.name)) return null
  const url = str(v.url)
  return {
    id: str(v.id) || `competitor-${index}`,
    name: str(v.name),
    neighborhood: str(v.neighborhood),
    distanceMi: num(v.distanceMi),
    rating: num(v.rating),
    reviewCount: num(v.reviewCount),
    itemPrice: num(v.itemPrice),
    waitMin: num(v.waitMin),
    priceChange90d: num(v.priceChange90d),
    complaints: parseComplaints(v.complaints),
    // Only plain web links; scraped strings must never become javascript: URLs.
    url: /^https?:\/\//i.test(url) ? url : undefined,
  }
}

function parseCompetitorsResponse(raw: unknown): CompetitorsResponse {
  if (!isObject(raw) || !Array.isArray(raw.competitors)) {
    throw new ApiError('The server sent competitors in an unexpected format.')
  }
  const competitors = raw.competitors
    .map(parseCompetitor)
    .filter((c): c is Competitor => c !== null)
    .sort((a, b) => (a.distanceMi ?? Infinity) - (b.distanceMi ?? Infinity))
  return {
    competitors,
    trends: Array.isArray(raw.trends) ? raw.trends.map(str).filter(Boolean) : [],
    source: raw.source === 'sample' ? 'sample' : 'live',
    scrapedAt: str(raw.scrapedAt) || new Date().toISOString(),
  }
}

const LEVELS: Impact[] = ['high', 'medium', 'low']
const level = (v: unknown): Impact => (LEVELS.includes(v as Impact) ? (v as Impact) : 'medium')

function parseRecommendationsResponse(raw: unknown): RecommendationsResponse {
  if (!isObject(raw) || !Array.isArray(raw.recommendations)) {
    throw new ApiError('The server sent tips in an unexpected format.')
  }
  const recommendations = raw.recommendations
    .filter(isObject)
    .map(
      (r, i): Recommendation => ({
        id: str(r.id) || `rec-${i}`,
        title: str(r.title),
        evidence: str(r.evidence),
        action: str(r.action),
        impact: level(r.impact),
        effort: level(r.effort),
      }),
    )
    .filter((r) => r.title)
  return { recommendations }
}
