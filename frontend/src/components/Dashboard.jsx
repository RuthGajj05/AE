import { BusinessHeader } from './BusinessHeader.jsx'
import { CompareCards } from './CompareCards.jsx'
import { CompetitorTable } from './CompetitorTable.jsx'
import { ComplaintThemes } from './ComplaintThemes.jsx'
import { EmptyState } from './States.jsx'
import { Suggestions } from './Suggestions.jsx'

export function Dashboard({ data, onLoadFile }) {
  const { business, competitors, themes, suggestions } = data
  const n = competitors.length

  return (
    <div className="dashboard">
      <BusinessHeader business={business} updatedAt={data.updatedAt} />

      <Section title="You vs nearby" subtitle={n ? `Compared with the average of ${n} nearby competitor${n === 1 ? '' : 's'}` : null}>
        {n ? (
          <CompareCards business={business} competitors={competitors} />
        ) : (
          <EmptyState
            title="No nearby competitors yet"
            text="Once the scraper finds businesses around you, they'll show up here."
            action={{ label: 'Load a JSON file', onClick: onLoadFile }}
          />
        )}
      </Section>

      {n > 0 && (
        <Section title="Who you're up against" subtitle="Nearest first">
          <CompetitorTable competitors={competitors} />
        </Section>
      )}

      <Section title="What customers complain about" subtitle="Across nearby competitors' reviews — every complaint is an opening for you">
        {themes.length ? (
          <ComplaintThemes themes={themes} />
        ) : (
          <EmptyState title="No review themes yet" text="Complaint themes appear here once reviews are analyzed." />
        )}
      </Section>

      <Section title="Claude's suggestions" subtitle="What to do next, based on the numbers above" claude>
        {suggestions.length ? (
          <Suggestions suggestions={suggestions} />
        ) : (
          <EmptyState title="No suggestions yet" text="Claude's suggestions appear here once the analysis runs." />
        )}
      </Section>
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
