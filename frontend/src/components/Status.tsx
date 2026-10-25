import { useEffect, useState } from 'react'

/** Shows each step in turn while the backend works, so a slow scrape still feels alive. */
export function LoadingCard({ steps }: { steps: string[] }) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), 2500)
    return () => clearInterval(timer)
  }, [steps.length])

  return (
    <section className="card loading" aria-busy="true" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p>{steps[step]}</p>
    </section>
  )
}

interface ErrorProps {
  title: string
  message: string
  onRetry: () => void
  onUseSample?: () => void
}

export function ErrorCard({ title, message, onRetry, onUseSample }: ErrorProps) {
  return (
    <section className="card error" role="alert">
      <div>
        <h3>{title}</h3>
        <p className="muted">{message}</p>
      </div>
      <div className="form-actions">
        {onUseSample && (
          <button className="btn ghost" onClick={onUseSample}>Use sample data</button>
        )}
        <button className="btn primary" onClick={onRetry}>Try again</button>
      </div>
    </section>
  )
}
