import { BusinessHeader } from './BusinessHeader.jsx'
import { Caveats } from './Caveats.jsx'
import { comparableMetrics } from '../compareMetrics.js'
import { CompareCards } from './CompareCards.jsx'
import { CompetitorTable } from './CompetitorTable.jsx'
import { ComplaintThemes } from './ComplaintThemes.jsx'
import { MarketGlance } from './MarketGlance.jsx'
import { PriceBenchmarks } from './PriceBenchmarks.jsx'
import { EmptyState } from './States.jsx'
import { Suggestions } from './Suggestions.jsx'

export function Dashboard({ data, onLoadFile }) {
  const { business, competitors, themes, benchmarks, suggestions, caveats } = data
  const n = competitors.length
  const shops = `${n} nearby competitor${n === 1 ? '' : 's'}`
  // "You vs nearby" needs the owner's own numbers; scraper reports often only have competitors.
  const canCompare = comparableMetrics(business, competitors).length > 0

  return (
    <div className="dashboard">
      <BusinessHeader business={business} summary={data.summary} reportDate={data.reportDate} dateOnly={data.dateOnly} />

      {n === 0 ? (
        <EmptyState
          title="No nearby competitors yet"
          text="Once the scraper finds businesses around you, they'll show up here."
          action={{ label: 'Load a JSON file', onClick: onLoadFile }}
        />
      ) : (
        <>
          <Section
            title={canCompare ? 'You vs nearby' : 'The market at a glance'}
            subtitle={canCompare ? `Compared with the average of ${shops}` : `What we found across ${shops}`}
          >
            {canCompare ? <CompareCards business={business} competitors={competitors} /> : <MarketGlance competitors={competitors} />}
          </Section>

          <Section title="Who you're up against" subtitle="Nearest first · tap a row for prices, praise, complaints and sources">
            <CompetitorTable competitors={competitors} />
          </Section>

          <Section title="What customers complain about" subtitle="Across nearby competitors' reviews — every complaint is an opening for you">
            {themes.length ? (
              <ComplaintThemes themes={themes} total={n} />
            ) : (
              <EmptyState title="No review complaints yet" text="Complaint themes appear here once reviews are analyzed." />
            )}
          </Section>

          {benchmarks.length > 0 && (
            <Section title="What things cost nearby" subtitle="Price ranges for common items across competitors">
              <PriceBenchmarks benchmarks={benchmarks} />
            </Section>
          )}
        </>
      )}

      <Section title="Claude's suggestions" subtitle="What to do next, with the evidence behind each one" claude>
        {suggestions.length ? (
          <Suggestions suggestions={suggestions} />
        ) : (
          <EmptyState title="No suggestions yet" text="Claude's suggestions appear here once the analysis runs." />
        )}
      </Section>

      {caveats.length > 0 && <Caveats caveats={caveats} />}
    </div>
  )
}

function Section({ title, subtitle, claude, children }) {
  return (
    <section className="section">
      <header className="section-head">
        <h2 className={claude ? 'claude-title' : undefined}>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </header>
      {children}
    </section>
  )
}
