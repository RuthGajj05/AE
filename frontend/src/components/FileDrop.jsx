import { IconUpload } from './Icons.jsx'

export function DropOverlay() {
  return (
    <div className="drop-overlay" aria-hidden="true">
      <div className="drop-card">
        <IconUpload size={28} />
        <strong>Drop the scraper's JSON</strong>
        <span>The dashboard updates instantly</span>
      </div>
    </div>
  )
}
