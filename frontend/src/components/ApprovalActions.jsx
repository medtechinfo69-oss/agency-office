import { useState } from 'react'
import { CheckCircle2, XCircle } from 'lucide-react'

// Both approval entry points share the same states and prevent duplicate decisions.
export default function ApprovalActions({ t, kind, onApprove }) {
  const [pending, setPending] = useState(null)
  const [error, setError] = useState('')
  const decide = async (approved) => {
    if (pending !== null) return
    setPending(approved); setError('')
    try { await onApprove(kind, approved) }
    catch (e) { setError(e.message || 'Could not submit the decision. Try again.') }
    finally { setPending(null) }
  }
  return (
    <div>
      <div className="approval-actions" aria-label="Approval decision" role="group">
        <button className="btn ghost" disabled={pending !== null} aria-busy={pending === false} onClick={() => decide(false)}>
          <XCircle size={16} /> {pending === false ? 'Submitting…' : t('reject')}
        </button>
        <button className="btn good" disabled={pending !== null} aria-busy={pending === true} onClick={() => decide(true)}>
          <CheckCircle2 size={16} /> {pending === true ? 'Approving…' : t('approve')}
        </button>
      </div>
      {error && <p className="np-err" role="alert">{error}</p>}
    </div>
  )
}
