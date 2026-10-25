// Checks a spot against Seattle's active business license records (Socrata, no key needed).
// Matching is on name + zip: a record whose name matches but whose zip doesn't is "unverified"
// rather than guessed. Results are cached in memory for the session, and this never throws.

const ENDPOINT = 'https://cos-data.seattle.gov/resource/wnbq-64tb.json'
const TIMEOUT_MS = 8000

export type LicenseStatus = 'verified' | 'unverified' | 'not_found' | 'error'

export interface LicenseMatch {
  legalName: string
  tradeName: string
  ownershipType: string
  openSince: number | null
  address: string
  zip: string
  naics: string
}

export interface LicenseCheck {
  status: LicenseStatus
  match: LicenseMatch | null
  /** Sole proprietorship or single-member LLC, and only for verified matches. */
  smallBusiness: boolean
  /** Why a match is unverified, or that the license address differs from the spot's. */
  note: string
}

interface LicenseRow {
  business_legal_name?: string
  trade_name?: string
  ownership_type?: string
  naics_description?: string
  license_start_date?: string
  street_address?: string
  zip?: string
}

const STOP_WORDS = new Set(['THE', 'AND', 'OF', 'A', 'AN', 'AT'])
// Dropped on the second, looser search ("Wild Rye Bakery" → WILD + RYE).
const GENERIC = new Set(['BAKERY', 'BAKERIES', 'BAKE', 'BAKING', 'BAKEHOUSE', 'CAFE', 'COFFEE', 'SHOP', 'CO', 'COMPANY', 'LLC', 'INC', 'SEATTLE'])
const SMALL_OWNERSHIP = new Set(['SOLE PROPRIETORSHIP', 'LLC - SINGLE MEMBER'])

const cache = new Map<string, Promise<LicenseCheck>>()

/** "Macrina Bakery – Aloha Café (Capitol Hill)" → ["MACRINA", "BAKERY"] */
function nameTokens(name: string): string[] {
  const core = name
    .replace(/\([^)]*\)/g, ' ')
    .split(/\s+[–—|-]\s+/)[0]
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
    .replace(/&/g, ' AND ')
    .replace(/[^A-Z0-9 ]/g, ' ')
  return core.split(/\s+/).filter((t) => t && !STOP_WORDS.has(t))
}

const zip5 = (s = '') => s.match(/\b(\d{5})(?:-\d{4})?\b/g)?.pop()?.slice(0, 5) ?? ''

const STREET_WORDS: Record<string, string> = { AVENUE: 'AVE', STREET: 'ST', EAST: 'E', WEST: 'W', NORTH: 'N', SOUTH: 'S', BOULEVARD: 'BLVD', DRIVE: 'DR', PLACE: 'PL', WAY: 'WAY' }
/** "137 15th Ave E, Seattle, WA 98112" → "137 15TH AVE E" */
function street(address = ''): string {
  return address
    .split(',')[0]
    .toUpperCase()
    .replace(/[^A-Z0-9 ]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => STREET_WORDS[w] ?? w)
    .join(' ')
}
const sameStreet = (a: string, b: string) => {
  const [an, ...aw] = street(a).split(' ')
  const [bn, ...bw] = street(b).split(' ')
  return !!an && an === bn && aw[0] === bw[0]
}

/** Share of the spot's name words found in the record's trade or legal name. */
function nameOverlap(spot: string[], row: LicenseRow): number {
  const score = (field = '') => {
    const words = new Set(nameTokens(field))
    return spot.filter((t) => words.has(t)).length / spot.length
  }
  return Math.max(score(row.trade_name), score(row.business_legal_name))
}

const soql = (t: string) => t.replace(/'/g, "''")
function whereAll(tokens: string[]): string {
  const field = (f: string) => tokens.map((t) => `upper(${f}) like '%${soql(t)}%'`).join(' AND ')
  return `(${field('trade_name')}) OR (${field('business_legal_name')})`
}

async function query(tokens: string[]): Promise<LicenseRow[]> {
  const url = `${ENDPOINT}?$where=${encodeURIComponent(whereAll(tokens))}&$limit=25`
  const res = await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS) })
  if (!res.ok) throw new Error(`License lookup failed (${res.status})`)
  const rows: unknown = await res.json()
  return Array.isArray(rows) ? (rows as LicenseRow[]) : []
}

function toMatch(row: LicenseRow): LicenseMatch {
  const year = Number((row.license_start_date ?? '').slice(0, 4))
  return {
    legalName: row.business_legal_name?.trim() ?? '',
    tradeName: row.trade_name?.trim() ?? '',
    ownershipType: row.ownership_type?.trim() ?? '',
    openSince: year > 1800 && year < 2100 ? year : null,
    address: row.street_address?.trim() ?? '',
    zip: zip5(row.zip),
    naics: row.naics_description?.trim() ?? '',
  }
}

async function check(name: string, address: string): Promise<LicenseCheck> {
  const tokens = nameTokens(name)
  if (!tokens.length) return { status: 'not_found', match: null, smallBusiness: false, note: '' }

  let rows = await query(tokens)
  const distinctive = tokens.filter((t) => !GENERIC.has(t))
  if (!rows.length && distinctive.length && distinctive.length < tokens.length && distinctive.some((t) => t.length >= 4)) {
    rows = await query(distinctive)
  }
  if (!rows.length) return { status: 'not_found', match: null, smallBusiness: false, note: '' }

  const zip = zip5(address)
  const scored = rows
    .map((row) => {
      const overlap = nameOverlap(tokens, row)
      const zipMatch = !!zip && zip5(row.zip) === zip
      const streetMatch = sameStreet(address, row.street_address ?? '')
      return { row, overlap, zipMatch, streetMatch, score: overlap * 2 + (zipMatch ? 1 : 0) + (streetMatch ? 2 : 0) }
    })
    .sort((a, b) => b.score - a.score)
  const best = scored[0]
  const match = toMatch(best.row)

  // Name plus location: the zip, or the exact street address when the zips disagree.
  if (best.overlap >= 0.6 && (best.zipMatch || best.streetMatch)) {
    return {
      status: 'verified',
      match,
      smallBusiness: SMALL_OWNERSHIP.has(match.ownershipType.toUpperCase()),
      note: !best.streetMatch ? `Licensed at ${match.address}` : !best.zipMatch ? `License records list zip ${match.zip}` : '',
    }
  }
  const note =
    best.overlap < 0.6
      ? `Closest record is “${match.tradeName || match.legalName}”`
      : `A “${match.tradeName || match.legalName}” is licensed at ${match.address} (${match.zip || 'no zip'}), not this address`
  return { status: 'unverified', match, smallBusiness: false, note }
}

export function verifyBusiness(name: string, address: string): Promise<LicenseCheck> {
  const key = `${name.toUpperCase()}|${zip5(address)}`
  let pending = cache.get(key)
  if (!pending) {
    pending = check(name, address).catch(() => {
      cache.delete(key) // let a later render try again
      return { status: 'error', match: null, smallBusiness: false, note: "Couldn't reach Seattle license records" } as LicenseCheck
    })
    cache.set(key, pending)
  }
  return pending
}
