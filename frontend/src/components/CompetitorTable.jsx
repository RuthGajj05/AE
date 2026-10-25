import { DASH, miles, minutes, money, stars } from '../format.js'

export function CompetitorTable({ competitors }) {
  return (
    <div className="glass table-card">
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th className="num">Distance</th>
            <th className="num">Rating</th>
            <th className="num">Price</th>
            <th className="num">Wait</th>
            <th>Top weakness</th>
          </tr>
        </thead>
        <tbody>
          {competitors.map((c) => (
            <tr key={c.id}>
              <td className="table-name">
                {c.url ? (
                  <a href={c.url} target="_blank" rel="noreferrer noopener">
                    {c.name}
                  </a>
                ) : (
                  c.name
                )}
              </td>
              <td className="num" data-label="Distance">{miles(c.distanceMi)}</td>
              <td className="num" data-label="Rating">
                {c.rating !== null && <span className="table-star">★</span>}
                {stars(c.rating)}
              </td>
              <td className="num" data-label="Price">{money(c.avgPrice)}</td>
              <td className="num" data-label="Wait">{minutes(c.waitMin)}</td>
              <td data-label="Top weakness">
                {c.topWeakness ? <span className="weakness">{c.topWeakness}</span> : <span className="muted">{DASH}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
