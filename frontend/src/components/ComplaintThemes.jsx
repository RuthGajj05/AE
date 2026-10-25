export function ComplaintThemes({ themes, total }) {
  const max = Math.max(...themes.map((t) => t.count), 1)

  return (
    <div className="glass themes">
      <ol className="theme-list">
        {themes.map((t) => (
          <li key={t.id} className="theme" tabIndex={t.quote ? 0 : undefined}>
            <div className="theme-row">
              <span className="theme-label">{t.label}</span>
              <span className="theme-count">
                {t.count.toLocaleString()}
                <span className="muted">
                  {t.unit === 'shops' ? ` of ${total} shops` : ` mention${t.count === 1 ? '' : 's'}`}
                </span>
              </span>
            </div>
            <div className="theme-track">
              <div className="theme-bar" style={{ width: `${(t.count / max) * 100}%` }} />
            </div>
            {t.quote && (
              <p className="theme-quote">
                “{t.quote}”{t.quoteBy && <span className="theme-quote-by"> — {t.quoteBy}</span>}
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  )
}
