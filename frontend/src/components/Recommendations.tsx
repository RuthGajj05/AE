import type { Recommendation } from '../types'

const capitalize = (s: string) => s[0].toUpperCase() + s.slice(1)

export function Recommendations({ items }: { items: Recommendation[] }) {
  if (items.length === 0) return null
  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h3>What to do next</h3>
          <p className="muted">Ranked by expected impact, then effort. Each one shows the numbers behind it.</p>
        </div>
      </header>
      <ol className="recs">
        {items.map((r) => (
          <li key={r.id} className="rec">
            <div className="rec-head">
              <h4>{r.title}</h4>
              <div className="chips">
                <span className={`chip impact-${r.impact}`}>{capitalize(r.impact)} impact</span>
                <span className="chip">{capitalize(r.effort)} effort</span>
              </div>
            </div>
            <p className="rec-evidence">{r.evidence}</p>
            <p className="rec-action">
              <span className="rec-action-label">Try this</span> {r.action}
            </p>
          </li>
        ))}
      </ol>
    </section>
  )
}
