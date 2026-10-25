export function ComplaintThemes({ themes }) {
  const max = Math.max(...themes.map((t) => t.mentions), 1)
  const total = themes.reduce((s, t) => s + t.mentions, 0)

  return (
    <div className="glass themes">
      <ol className="theme-list">
        {themes.map((t) => (
          <li key={t.id} className="theme" tabIndex={t.quote ? 0 : undefined}>
            <div className="theme-row">
              <span className="theme-label">{t.label}</span>
              <span className="theme-count">
                {t.mentions.toLocaleString()}
                <span className="muted"> mention{t.mentions === 1 ? '' : 's'}</span>
              </span>
            </div>
            <div className="theme-track">
              <div
                className="theme-bar"
                style={{ width: `${(t.mentions / max) * 100}%` }}
                title={total ? `${Math.round((t.mentions / total) * 100)}% of all complaints` : undefined}
              />
            </div>
            {t.quote && <p className="theme-quote">“{t.quote}”</p>}
          </li>
        ))}
      </ol>
    </div>
  )
}
