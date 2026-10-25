import { average } from '../data/adapter.js'
import { count, miles, stars } from '../format.js'

function siteName(url) {
  try {
    return new URL(url).hostname.replace(/^(www|m)\./, '')
  } catch {
    return null
  }
}

export function MarketGlance({ competitors }) {
  const n = competitors.length
  const rated = competitors.filter((c) => c.rating !== null)
  const avgRating = average(competitors, 'rating')
  const reviews = competitors.reduce((s, c) => s + (c.reviewCount ?? 0), 0)
  const sources = competitors.flatMap((c) => c.sources)
  const sites = new Set(sources.map(siteName).filter(Boolean))
  const nearest = competitors.find((c) => c.distanceMi !== null)

  const tiles = [
    { label: 'Competitors', value: n, detail: nearest ? `Closest is ${miles(nearest.distanceMi)} away` : 'Near you' },
    {
      label: 'Average rating',
      value: avgRating === null ? '—' : `${stars(avgRating)}★`,
      detail: rated.length ? `${rated.length} of ${n} have a rating` : 'No ratings found',
    },
    { label: 'Reviews read', value: reviews ? count(reviews) : '—', detail: `Across ${n} shops` },
    { label: 'Sources checked', value: sources.length || '—', detail: sites.size ? `From ${sites.size} different sites` : 'Linked per shop' },
  ]

  return (
    <div className="glance-grid">
      {tiles.map((t) => (
        <article key={t.label} className="glass glance">
          <span className="glance-label">{t.label}</span>
          <span className="glance-value">{t.value}</span>
          <span className="glance-detail">{t.detail}</span>
        </article>
      ))}
    </div>
  )
}
