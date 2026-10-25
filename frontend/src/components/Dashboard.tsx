import { useMemo, useState } from 'react'
import { CATEGORIES, NEIGHBORHOODS, THEMES } from '../data/reference'
import { COMPETITORS, TRENDS } from '../data/sample'
import { analyze, money, pct } from '../lib/insights'
import type { Profile } from '../types'
import { BarChart, type BarRow } from './BarChart'
import { CompetitorTable } from './CompetitorTable'
import { Recommendations } from './Recommendations'
import { StatTile } from './StatTile'

const RADII = [
  { mi: 2, label: 'Within 2 mi' },
  { mi: 4, label: 'Within 4 mi' },
  { mi: 15, label: 'All Seattle' },
]

export function Dashboard({ profile }: { profile: Profile }) {
  const [radius, setRadius] = useState(4)
  const a = useMemo(() => analyze(profile, COMPETITORS, radius), [profile, radius])
  const { item, plural } = CATEGORIES[profile.category]
  const n = a.nearby.length

  const barRows = (value: (c: { itemPrice: number; waitMin: number }) => number): BarRow[] =>
    [
      { id: 'you', label: `${profile.name} (you)`, value: value(profile), highlight: true, detail: NEIGHBORHOODS[profile.neighborhood].label },
      ...a.nearby.map((c) => ({
        id: c.id,
        label: c.name,
        value: value(c),
        detail: `${NEIGHBORHOODS[c.neighborhood].label} · ${c.distance.toFixed(1)} mi · ${c.rating.toFixed(1)}★`,
      })),
    ].sort((x, y) => y.value - x.value)

  const themeRows: BarRow[] = a.themes.map((t) => ({
    id: t.theme,
    label: THEMES[t.theme].label,
    value: t.mentions,
    detail: `${t.businesses} of ${n} ${plural}`,
  }))

  const raised = a.nearby.filter((c) => c.priceChange90d > 0)
  const avgRaise = raised.length ? raised.reduce((s, c) => s + c.priceChange90d, 0) / raised.length : 0

  return (
    <div className="dashboard">
      <div className="filter-row" role="group" aria-label="Compare against">
        <span className="muted">Compare against</span>
        {RADII.map((r) => (
          <button
            key={r.mi}
            className={`seg${radius === r.mi ? ' is-active' : ''}`}
            aria-pressed={radius === r.mi}
            onClick={() => setRadius(r.mi)}
          >
            {r.label}
          </button>
        ))}
        <span className="muted count">{n} {plural} found</span>
      </div>

      {n === 0 ? (
        <section className="card empty">
          <h3>No {plural} in this range yet</h3>
          <p className="muted">Widen the range to compare against more of Seattle.</p>
        </section>
      ) : (
        <>
          <div className="stats">
            <StatTile
              label={`Your ${item} price`}
              value={pct(a.priceGap)}
              detail={`${money(profile.itemPrice)} vs ${money(a.medianPrice)} median`}
              tone={Math.abs(a.priceGap) < 0.08 ? 'neutral' : a.priceGap < 0 ? 'good' : 'bad'}
            />
            <StatTile
              label="Your wait"
              value={`${a.waitGap > 0 ? '+' : ''}${Math.round(a.waitGap)} min`}
              detail={`${profile.waitMin} min vs ${a.medianWait} min median`}
              tone={Math.abs(a.waitGap) < 2 ? 'neutral' : a.waitGap < 0 ? 'good' : 'bad'}
            />
            <StatTile
              label="Your rating"
              value={profile.rating.toFixed(1)}
              detail={`${a.medianRating.toFixed(1)} median nearby`}
              tone={profile.rating > a.medianRating ? 'good' : profile.rating < a.medianRating ? 'bad' : 'neutral'}
            />
            <StatTile
              label="Your reviews"
              value={profile.reviewCount.toLocaleString()}
              detail={`${Math.round(a.medianReviews).toLocaleString()} median nearby`}
              tone={profile.reviewCount >= a.medianReviews ? 'good' : 'bad'}
            />
          </div>

          <Recommendations items={a.recommendations} />

          <div className="grid-2">
            <BarChart
              title={`Price of a ${item}`}
              subtitle={`You and ${n} nearby ${plural}`}
              rows={barRows((c) => c.itemPrice)}
              format={money}
              reference={{ value: a.medianPrice, label: `Nearby median ${money(a.medianPrice)}` }}
            />
            <BarChart
              title="Typical wait"
              subtitle="Minutes from ordering to food in hand"
              rows={barRows((c) => c.waitMin)}
              format={(v) => `${v} min`}
              reference={{ value: a.medianWait, label: `Nearby median ${a.medianWait} min` }}
            />
          </div>

          <div className="grid-2">
            <BarChart
              title="What customers complain about nearby"
              subtitle="Review mentions across your competitors — each one is an opening for you"
              rows={themeRows}
              format={(v) => `${v}`}
            />
            <section className="card">
              <header className="card-head">
                <div>
                  <h3>Market signals</h3>
                  <p className="muted">What's moving for {plural} in Seattle</p>
                </div>
              </header>
              <ul className="signals">
                <li>
                  <strong>{raised.length} of {n}</strong> nearby {plural} raised their {item} price in the last 90 days
                  {raised.length > 0 && <> (average {pct(avgRaise / 100)})</>}.
                </li>
                {TRENDS[profile.category].map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </section>
          </div>

          <CompetitorTable rows={a.nearby} item={item} />
        </>
      )}
    </div>
  )
}
