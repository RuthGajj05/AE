import { Fragment, useState } from 'react'
import { count, DASH, miles, minutes, money, stars } from '../format.js'

function siteName(url) {
  try {
    return new URL(url).hostname.replace(/^(www|m)\./, '')
  } catch {
    return url
  }
}

function DetailList({ title, items }) {
  if (!items.length) return null
  return (
    <div className="detail-block">
      <h4>{title}</h4>
      <ul>
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function Details({ c }) {
  return (
    <div className="details">
      <DetailList title="Known for" items={c.specialties.slice(0, 4)} />
      <DetailList title="Praised for" items={c.praisedFor.slice(0, 4)} />
      <DetailList title="Complaints" items={c.complaints} />
      <DetailList title="Prices" items={c.prices.map((p) => `${p.item}: ${money(p.price)}`)} />
      <div className="detail-block detail-sources">
        <h4>Sources</h4>
        <div className="source-chips">
          {c.url && (
            <a className="source-chip is-site" href={c.url} target="_blank" rel="noreferrer noopener">
              Website ↗
            </a>
          )}
          {c.sources.map((url, i) => (
            <a key={i} className="source-chip" href={url} target="_blank" rel="noreferrer noopener" title={url}>
              {siteName(url)}
            </a>
          ))}
          {!c.url && !c.sources.length && <span className="muted">No links in this report</span>}
        </div>
        {c.address && <p className="detail-address">{c.address}</p>}
        {c.distanceNote && <p className="detail-address">Distance: {c.distanceNote}</p>}
      </div>
    </div>
  )
}

export function CompetitorTable({ competitors }) {
  const [open, setOpen] = useState(null)
  const showWait = competitors.some((c) => c.waitMin !== null)
  const showPrice = competitors.some((c) => c.minPrice !== null || c.avgPrice !== null)
  const columns = 4 + (showWait ? 1 : 0) + (showPrice ? 1 : 0)
  const toggle = (id) => setOpen((o) => (o === id ? null : id))

  return (
    <div className="glass table-card">
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th className="num">Distance</th>
            <th className="num">Rating</th>
            {showPrice && <th className="num">Items from</th>}
            {showWait && <th className="num">Wait</th>}
            <th>Top weakness</th>
          </tr>
        </thead>
        <tbody>
          {competitors.map((c) => {
            const isOpen = open === c.id
            return (
              <Fragment key={c.id}>
                <tr
                  className={`row${isOpen ? ' is-open' : ''}`}
                  tabIndex={0}
                  aria-expanded={isOpen}
                  onClick={() => toggle(c.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      toggle(c.id)
                    }
                  }}
                >
                  <td className="table-name">
                    <span className="chevron" aria-hidden="true" />
                    {c.name}
                  </td>
                  <td className="num" data-label="Distance">{miles(c.distanceMi)}</td>
                  <td className="num" data-label="Rating">
                    {c.rating !== null && <span className="table-star">★</span>}
                    {stars(c.rating)}
                    {c.reviewCount !== null && <span className="muted table-reviews"> ({count(c.reviewCount)})</span>}
                  </td>
                  {showPrice && <td className="num" data-label="Items from">{money(c.minPrice ?? c.avgPrice)}</td>}
                  {showWait && <td className="num" data-label="Wait">{minutes(c.waitMin)}</td>}
                  <td data-label="Top weakness">
                    {c.topWeakness ? <span className="weakness">{c.topWeakness}</span> : <span className="muted">{DASH}</span>}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="detail-row">
                    <td colSpan={columns}>
                      <Details c={c} />
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
