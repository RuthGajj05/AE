import { THEMES } from '../data/reference'
import { money, pct } from '../lib/stats'
import type { Competitor, Theme } from '../types'

const DASH = '—'
const show = <T,>(v: T | null, fmt: (v: T) => string) => (v === null ? DASH : fmt(v))

function topComplaint(c: Competitor): string {
  const [theme] = (Object.entries(c.complaints) as [Theme, number][]).sort((a, b) => b[1] - a[1])[0] ?? []
  return theme ? THEMES[theme].label : DASH
}

export function CompetitorTable({ rows, item }: { rows: Competitor[]; item: string }) {
  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h3>Who you're up against</h3>
          <p className="muted">Nearest first. Price is for a {item}. “—” means we couldn't find it.</p>
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
                <td className="strong">
                  {c.url ? <a href={c.url} target="_blank" rel="noreferrer noopener">{c.name}</a> : c.name}
                </td>
                <td>{c.neighborhood || DASH}</td>
                <td className="num">{show(c.distanceMi, (d) => (d < 0.1 ? 'Same area' : `${d.toFixed(1)} mi`))}</td>
                <td className="num">{show(c.rating, (r) => r.toFixed(1))}</td>
                <td className="num">{show(c.reviewCount, (r) => r.toLocaleString())}</td>
                <td className="num">{show(c.itemPrice, money)}</td>
                <td className="num">{show(c.priceChange90d, (p) => (p === 0 ? 'No change' : pct(p / 100)))}</td>
                <td className="num">{show(c.waitMin, (w) => `${w} min`)}</td>
                <td>{topComplaint(c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
