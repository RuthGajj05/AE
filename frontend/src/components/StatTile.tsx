interface Props {
  label: string
  value: string
  detail: string
  tone?: 'good' | 'bad' | 'neutral'
}

const TONE_ICON = { good: '▲', bad: '▼', neutral: '•' }

export function StatTile({ label, value, detail, tone = 'neutral' }: Props) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      <span className={`stat-detail tone-${tone}`}>
        <span aria-hidden="true">{TONE_ICON[tone]}</span> {detail}
      </span>
    </div>
  )
}
