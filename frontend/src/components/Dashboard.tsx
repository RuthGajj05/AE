import { useEffect, useMemo, useState } from 'react'
import { getCompetitors, getRecommendations, usingMocks } from '../api/client'
import { CATEGORIES, NEIGHBORHOODS, THEMES } from '../data/reference'
import { marketStats, money, pct } from '../lib/stats'
import type { CompetitorsResponse, Profile, Recommendation } from '../types'
import { BarChart, type BarRow } from './BarChart'
import { CompetitorTable } from './CompetitorTable'
import { ErrorCard, LoadingCard } from './Status'
import { Recommendations } from './Recommendations'
import { StatTile } from './StatTile'

const RADII = [
  { mi: 2, label: 'Within 2 mi' },
  { mi: 4, label: 'Within 4 mi' },
  { mi: 15, label: 'All Seattle' },
]

type Load<T> = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: T }

const errorMessage = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong.')

function useMarket(profile: Profile, radius: number) {
  const [attempt, setAttempt] = useState(0)
  const [market, setMarket] = useState<Load<CompetitorsResponse>>({ status: 'loading' })
  const [tips, setTips] = useState<Load<Recommendation[]>>({ status: 'loading' })

  useEffect(() => {
    const ctrl = new AbortController()
    ;(async () => {
      let data: CompetitorsResponse
      try {
        data = await getCompetitors(profile, radius, ctrl.signal)
      } catch (e) {
        if (!ctrl.signal.aborted) setMarket({ status: 'error', message: errorMessage(e) })
        return
      }
      setMarket({ status: 'ready', data })
      if (data.competitors.length === 0) {
        setTips({ status: 'ready', data: [] })
        return
      }
      try {
        const { recommendations } = await getRecommendations(profile, data.competitors, ctrl.signal)
        setTips({ status: 'ready', data: recommendations })
      } catch (e) {
        if (!ctrl.signal.aborted) setTips({ status: 'error', message: errorMessage(e) })
      }
    })()
    return () => ctrl.abort()
  }, [profile, radius, attempt])

  // Loading is set by whatever starts a new request; a profile change remounts the dashboard.
  const reload = () => {
    setMarket({ status: 'loading' })
    setTips({ status: 'loading' })
    setAttempt((a) => a + 1)
  }
  return { market, tips, reload }
}

function switchToSampleData() {
  const params = new URLSearchParams(window.location.search)
  params.set('mock', '')
  window.location.search = params.toString()
}

export function Dashboard({ profile }: { profile: Profile }) {
  const [radius, setRadius] = useState(4)
  const { market, tips, reload } = useMarket(profile, radius)
  const changeRadius = (mi: number) => {
    if (mi === radius) return
    setRadius(mi)
    reload()
  }
  const { plural } = CATEGORIES[profile.category]

  return (
    <div className="dashboard">
      <div className="filter-row" role="group" aria-label="Compare against">
        <span className="muted">Compare against</span>
        {RADII.map((r) => (
          <button
            key={r.mi}
            className={`seg${radius === r.mi ? ' is-active' : ''}`}
            aria-pressed={radius === r.mi}
            onClick={() => changeRadius(r.mi)}
          >
            {r.label}
          </button>
        ))}
        {market.status === 'ready' && (
          <span className="muted count">
            {market.data.competitors.length} {plural} found
            <SourceBadge source={market.data.source} scrapedAt={market.data.scrapedAt} />
          </span>
        )}
      </div>

      {market.status === 'loading' && (
        <LoadingCard
          steps={[`Finding ${plural} near ${NEIGHBORHOODS[profile.neighborhood].label}…`, 'Reading their reviews…', 'Comparing prices and wait times…']}
        />
      )}
      {market.status === 'error' && (
        <ErrorCard
          title="Couldn't load your competitors"
          message={market.message}
          onRetry={reload}
          onUseSample={usingMocks ? undefined : switchToSampleData}
        />
      )}
      {market.status === 'ready' && (
        <MarketView profile={profile} market={market.data} tips={tips} onRetry={reload} />
      )}
    </div>
  )
}

function SourceBadge({ source, scrapedAt }: { source: CompetitorsResponse['source']; scrapedAt: string }) {
  if (source === 'sample') return <span className="badge">Sample data</span>
  const time = new Date(scrapedAt)
  const label = Number.isNaN(time.getTime()) ? 'Live' : `Live · ${time.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
  return <span className="badge is-live">{label}</span>
}

interface MarketViewProps {
  profile: Profile
  market: CompetitorsResponse
  tips: Load<Recommendation[]>
  onRetry: () => void
}

function MarketView({ profile, market, tips, onRetry }: MarketViewProps) {
  const { competitors, trends, source } = market
  const s = useMemo(() => marketStats(profile, competitors), [profile, competitors])
  const { item, plural } = CATEGORIES[profile.category]
  const n = competitors.length

  if (n === 0) {
    return (
      <section className="card empty">
        <h3>No {plural} found in this range</h3>
        <p className="muted">Widen the range to compare against more of Seattle.</p>
      </section>
    )
  }

  const barRows = (pick: (c: { itemPrice: number | null; waitMin: number | null }) => number | null): BarRow[] => {
    const rows: BarRow[] = [
      { id: 'you', label: `${profile.name} (you)`, value: pick(profile)!, highlight: true, detail: NEIGHBORHOODS[profile.neighborhood].label },
    ]
    for (const c of competitors) {
      const value = pick(c)
      if (value === null) continue
      const where = [c.neighborhood, c.distanceMi !== null && `${c.distanceMi.toFixed(1)} mi`, c.rating !== null && `${c.rating.toFixed(1)}★`]
      rows.push({ id: c.id, label: c.name, value, detail: where.filter(Boolean).join(' · ') })
    }
    return rows.sort((a, b) => b.value - a.value)
  }
  const coverage = (pick: (c: (typeof competitors)[number]) => number | null, what: string) => {
    const missing = competitors.filter((c) => pick(c) === null).length
    return missing ? ` · ${missing} without a listed ${what}` : ''
  }

  const themeRows: BarRow[] = s.themes.map((t) => ({
    id: t.theme,
    label: THEMES[t.theme].label,
    value: t.mentions,
    detail: `${t.businesses} of ${n} ${plural}`,
  }))

  const priced = n - competitors.filter((c) => c.itemPrice === null).length

  return (
    <>
      <div className="stats">
        <StatTile
          label={`Your ${item} price`}
          value={s.priceGap === null ? money(profile.itemPrice) : pct(s.priceGap)}
          detail={s.medianPrice === null ? 'No nearby prices found yet' : `${money(profile.itemPrice)} vs ${money(s.medianPrice)} median`}
          tone={s.priceGap === null || Math.abs(s.priceGap) < 0.08 ? 'neutral' : s.priceGap < 0 ? 'good' : 'bad'}
        />
        <StatTile
          label="Your wait"
          value={s.waitGap === null ? `${profile.waitMin} min` : `${s.waitGap > 0 ? '+' : ''}${Math.round(s.waitGap)} min`}
          detail={s.medianWait === null ? 'No nearby wait times found yet' : `${profile.waitMin} min vs ${s.medianWait} min median`}
          tone={s.waitGap === null || Math.abs(s.waitGap) < 2 ? 'neutral' : s.waitGap < 0 ? 'good' : 'bad'}
        />
        <StatTile
          label="Your rating"
          value={profile.rating.toFixed(1)}
          detail={s.medianRating === null ? 'No nearby ratings found yet' : `${s.medianRating.toFixed(1)} median nearby`}
          tone={s.medianRating === null || profile.rating === s.medianRating ? 'neutral' : profile.rating > s.medianRating ? 'good' : 'bad'}
        />
        <StatTile
          label="Your reviews"
          value={profile.reviewCount.toLocaleString()}
          detail={s.medianReviews === null ? 'No nearby review counts yet' : `${Math.round(s.medianReviews).toLocaleString()} median nearby`}
          tone={s.medianReviews === null ? 'neutral' : profile.reviewCount >= s.medianReviews ? 'good' : 'bad'}
        />
      </div>

      {tips.status === 'loading' && <LoadingCard steps={['Claude is reading the numbers…', 'Writing your tips…']} />}
      {tips.status === 'error' && <ErrorCard title="Couldn't load your tips" message={tips.message} onRetry={onRetry} />}
      {tips.status === 'ready' && <Recommendations items={tips.data} />}

      <div className="grid-2">
        <BarChart
          title={`Price of a ${item}`}
          subtitle={`You and ${priced} nearby ${plural}${coverage((c) => c.itemPrice, 'price')}`}
          rows={barRows((c) => c.itemPrice)}
          format={money}
          reference={s.medianPrice === null ? undefined : { value: s.medianPrice, label: `Nearby median ${money(s.medianPrice)}` }}
        />
        <BarChart
          title="Typical wait"
          subtitle={`Minutes from ordering to food in hand${coverage((c) => c.waitMin, 'wait time')}`}
          rows={barRows((c) => c.waitMin)}
          format={(v) => `${v} min`}
          reference={s.medianWait === null ? undefined : { value: s.medianWait, label: `Nearby median ${s.medianWait} min` }}
        />
      </div>

      <div className="grid-2">
        {themeRows.length > 0 ? (
          <BarChart
            title="What customers complain about nearby"
            subtitle="Review mentions across your competitors — each one is an opening for you"
            rows={themeRows}
            format={(v) => `${v}`}
          />
        ) : (
          <section className="card">
            <h3>What customers complain about nearby</h3>
            <p className="muted">No review complaints found for these competitors yet.</p>
          </section>
        )}
        <section className="card">
          <header className="card-head">
            <div>
              <h3>Market signals</h3>
              <p className="muted">What's moving for {plural} in Seattle</p>
            </div>
          </header>
          <ul className="signals">
            {s.priceTracked > 0 && (
              <li>
                <strong>{s.priceRaisers} of {s.priceTracked}</strong> nearby {plural} raised their {item} price in the last 90 days
                {s.priceRaisers > 0 && <> (average {pct(s.avgRaise / 100)})</>}.
              </li>
            )}
            {trends.map((t) => (
              <li key={t}>{t}</li>
            ))}
            {s.priceTracked === 0 && trends.length === 0 && <li className="muted">No signals yet for this area.</li>}
          </ul>
        </section>
      </div>

      <CompetitorTable rows={competitors} item={item} />

      {source === 'sample' && (
        <p className="notice">
          Sample data: these competitors and trends are fictional Seattle businesses, shown until live research is connected.
        </p>
      )}
    </>
  )
}
