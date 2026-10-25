import { IconSparkle } from './Icons.jsx'

const IMPACT_LABEL = { high: 'High impact', medium: 'Medium impact', low: 'Low impact' }

export function Suggestions({ suggestions }) {
  return (
    <div className="suggestion-grid">
      {suggestions.map((s, i) => (
        <article key={s.id} className={`glass suggestion${i === 0 ? ' is-top' : ''}${s.impact ? ` impact-${s.impact}` : ''}`}>
          <div className="suggestion-top">
            <span className="suggestion-index">
              <IconSparkle size={14} />
              {String(i + 1).padStart(2, '0')}
            </span>
            {s.impact && <span className={`badge badge-${s.impact}`}>{IMPACT_LABEL[s.impact]}</span>}
          </div>
          <h3>{s.title}</h3>
          {s.why && <p>{s.why}</p>}
          {s.evidence && (
            <details className="evidence">
              <summary>Why Claude suggests this</summary>
              <p>{s.evidence}</p>
            </details>
          )}
        </article>
      ))}
    </div>
  )
}
