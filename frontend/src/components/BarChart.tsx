import { useState, type CSSProperties } from 'react'

export interface BarRow {
  id: string
  label: string
  value: number
  detail?: string
  /** Marks the user's own business; every other bar is drawn muted. */
  highlight?: boolean
}

interface Props {
  title: string
  subtitle?: string
  rows: BarRow[]
  format: (v: number) => string
  reference?: { value: number; label: string }
}

export function BarChart({ title, subtitle, rows, format, reference }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)
  const [asTable, setAsTable] = useState(false)
  const emphasis = rows.some((r) => r.highlight)
  // Leave headroom so the value label at the bar tip always fits.
  const max = Math.max(...rows.map((r) => r.value), reference?.value ?? 0) * 1.25 || 1
  const frac = (v: number) => v / max

  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h3>{title}</h3>
          {subtitle && <p className="muted">{subtitle}</p>}
        </div>
        <button className="text-btn" onClick={() => setAsTable((t) => !t)}>
          {asTable ? 'Show chart' : 'Show table'}
        </button>
      </header>

      {asTable ? (
        <table className="data-table compact">
          <thead>
            <tr>
              <th>Business</th>
              <th className="num">Value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={r.highlight ? 'is-you' : undefined}>
                <td>{r.label}</td>
                <td className="num">{format(r.value)}</td>
              </tr>
            ))}
            {reference && (
              <tr>
                <td className="muted">{reference.label}</td>
                <td className="num muted">{format(reference.value)}</td>
              </tr>
            )}
          </tbody>
        </table>
      ) : (
        <>
          {(emphasis || reference) && (
            <div className="legend">
              {emphasis && (
                <>
                  <span><i className="swatch is-you" />You</span>
                  <span><i className="swatch is-muted" />Nearby</span>
                </>
              )}
              {reference && <span><i className="swatch-line" />{reference.label}</span>}
            </div>
          )}
          <div className="bars">
            {rows.map((r) => {
              const w = frac(r.value) * 100
              const tone = r.highlight ? ' is-you' : emphasis ? ' is-muted' : ''
              return (
                <div
                  key={r.id}
                  className="bar-row"
                  tabIndex={0}
                  onMouseEnter={() => setHovered(r.id)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(r.id)}
                  onBlur={() => setHovered(null)}
                >
                  <span className={`bar-label${r.highlight ? ' strong' : ''}`} title={r.label}>
                    {r.label}
                  </span>
                  <div className="bar-track">
                    <div className={`bar${tone}`} style={{ width: `${w}%` }} />
                    <span className="bar-value" style={{ left: `calc(${w}% + 6px)` }}>
                      {format(r.value)}
                    </span>
                    {hovered === r.id && (
                      <div className="tooltip" role="tooltip" style={{ left: `${Math.min(w, 70)}%` }}>
                        <strong>{r.label}</strong>
                        <span>{format(r.value)}</span>
                        {r.detail && <span className="muted">{r.detail}</span>}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
            {reference && (
              <div
                className="ref-line"
                style={{ '--ref': frac(reference.value) } as CSSProperties}
                aria-hidden="true"
              />
            )}
          </div>
        </>
      )}
    </section>
  )
}
