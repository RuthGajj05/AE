export function LoadingView() {
  return (
    <div className="dashboard" aria-busy="true" aria-label="Loading dashboard">
      <div className="hero">
        <div className="hero-main">
          <span className="skeleton" style={{ width: 180, height: 22 }} />
          <span className="skeleton" style={{ width: 'min(420px, 80%)', height: 44 }} />
        </div>
      </div>
      <p className="loading-text">Loading the latest competitor report…</p>
      <div className="compare-grid">
        {[0, 1, 2].map((i) => (
          <div key={i} className="glass compare">
            <span className="skeleton" style={{ width: '40%', height: 14 }} />
            <span className="skeleton" style={{ width: '55%', height: 36 }} />
            <span className="skeleton" style={{ width: '100%', height: 10 }} />
          </div>
        ))}
      </div>
      <div className="glass table-card skeleton-table">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className="skeleton" style={{ width: '100%', height: 18 }} />
        ))}
      </div>
    </div>
  )
}

export function EmptyState({ title, text, action }) {
  return (
    <div className="glass empty">
      <h3>{title}</h3>
      <p>{text}</p>
      {action && (
        <button className="btn" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  )
}

export function ErrorView({ message, onRetry, onUseSaved }) {
  return (
    <div className="glass empty error" role="alert">
      <h3>Couldn't load the dashboard</h3>
      <p>{message}</p>
      <div className="empty-actions">
        <button className="btn" onClick={onUseSaved}>Use saved report</button>
        <button className="btn btn-primary" onClick={onRetry}>Try again</button>
      </div>
      <p className="muted small">Or drop the scraper's JSON file anywhere on this page.</p>
    </div>
  )
}
