// Geocodes every competitor address in a scraper report once, with the free US Census geocoder,
// and saves the results to data/spots.geo.json so the map never geocodes during the demo.
//
//   node scripts/geocode-spots.mjs [report.json] [out.json]
//
// Defaults: src/data/capitol-hill-bakery-report.json → data/spots.geo.json. Addresses that fail are
// logged and saved under "failed"; their spots still show in the list, just without a pin.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const input = resolve(process.argv[2] ?? `${root}/src/data/capitol-hill-bakery-report.json`)
const output = resolve(process.argv[3] ?? `${root}/data/spots.geo.json`)
const ENDPOINT = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function geocode(address) {
  const url = `${ENDPOINT}?address=${encodeURIComponent(address)}&benchmark=Public_AR_Current&format=json`
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(20_000) })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const match = (await res.json())?.result?.addressMatches?.[0]
      if (!match) return { error: 'no match' }
      return { lat: match.coordinates.y, lng: match.coordinates.x, matchedAddress: match.matchedAddress }
    } catch (err) {
      if (attempt === 3) return { error: err.message }
      await sleep(1000 * attempt)
    }
  }
}

/** "1435 E John St # 137, Seattle" → "1435 E John St, Seattle": unit numbers often trip the geocoder. */
// Whole words only, so street names like "Stewart St" or "Westlake Ave" survive.
const withoutUnit = (a) => a.replace(/\s*(?:#\s*|\b(?:suite|ste|unit|apt)\b\.?\s*)[\w-]+/gi, '').replace(/\s+,/g, ',')

const report = JSON.parse(readFileSync(input, 'utf8'))
const competitors = Array.isArray(report.competitors) ? report.competitors : []
const spots = []
const failed = []

for (const c of competitors) {
  const address = typeof c.address === 'string' ? c.address.trim() : ''
  if (!c.name || !address) {
    failed.push({ name: c.name ?? '(no name)', address, error: 'no address in report' })
    console.log(`✗ ${c.name}: no address in report`)
    continue
  }
  let result = await geocode(address)
  if (result.error && withoutUnit(address) !== address) result = await geocode(withoutUnit(address))
  if (result.error) {
    failed.push({ name: c.name, address, error: result.error })
    console.log(`✗ ${c.name}: ${address} (${result.error})`)
  } else {
    spots.push({ name: c.name, address, ...result })
    console.log(`✓ ${c.name}: ${result.lat.toFixed(5)}, ${result.lng.toFixed(5)}  (${result.matchedAddress})`)
  }
  await sleep(250)
}

mkdirSync(dirname(output), { recursive: true })
writeFileSync(
  output,
  JSON.stringify({ source: input.replace(`${root}/`, ''), geocoder: 'US Census (Public_AR_Current)', generatedAt: new Date().toISOString(), spots, failed }, null, 2) + '\n',
)
console.log(`\n${spots.length} geocoded, ${failed.length} failed → ${output.replace(`${root}/`, '')}`)
