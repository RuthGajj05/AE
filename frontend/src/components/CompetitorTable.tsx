import { NEIGHBORHOODS, THEMES } from '../data/reference'
import { money, pct, type NearbyCompetitor } from '../lib/insights'
import type { Theme } from '../types'

function topComplaint(c: NearbyCompetitor): string {
  const [theme] = (Object.entries(c.complaints) as [Theme, number][]).sort((a, b) => b[1] - a[1])[0] ?? []
  return theme ? THEMES[theme].label : '—'
}

export function CompetitorTable({ rows, item }: { rows: NearbyCompetitor[]; item: string }) {
  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h3>Who you're up against</h3>
          <p className="muted">Nearest first. Price is for a {item}.</p>
        </div>
      </header>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Business</th>
              <th>Neighborhood</th>
              <th className="num">Distance</th>
              <th className="num">Rating</th>
              <th className="num">Reviews</th>
              <th className="num">Price</th>
              <th className="num">90-day change</th>
              <th className="num">Wait</th>
              <th>Top complaint</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id}>
                <td className="strong">{c.name}</td>
                <td>{NEIGHBORHOODS[c.neighborhood].label}</td>
                <td className="num">{c.distance < 0.1 ? 'Same area' : `${c.distance.toFixed(1)} mi`}</td>
                <td className="num">{c.rating.toFixed(1)}</td>
                <td className="num">{c.reviewCount.toLocaleString()}</td>
                <td className="num">{money(c.itemPrice)}</td>
                <td className="num">{c.priceChange90d === 0 ? '—' : pct(c.priceChange90d / 100)}</td>
                <td className="num">{c.waitMin} min</td>
                <td>{topComplaint(c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
