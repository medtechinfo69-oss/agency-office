import useDialog from './useDialog'
import { useEffect, useState } from 'react'
import { api } from '../api'

/* Analytics dashboard: paste campaign results → agents learn what performs */
export default function AnalyticsScreen({ t, projectId, onClose }) {
  const dialogRef = useDialog(onClose)
  const [rows, setRows] = useState([])
  const [form, setForm] = useState({ campaign: '', reach: '', clicks: '', spend: '', ctr: '', notes: '' })
  const [insight, setInsight] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')

  const load = () => api.analytics(projectId).then(setRows).catch((e) => setToast('⚠ ' + e.message))
  useEffect(() => { load() }, [projectId]) // eslint-disable-line

  const add = async (e) => {
    e.preventDefault()
    if (!form.campaign.trim()) { setToast('Enter a campaign name, not just spaces.'); return }
    setBusy(true)
    try {
      const metrics = {}
      for (const k of ['reach', 'clicks', 'spend', 'ctr']) {
        if (form[k] !== '') metrics[k] = Number(form[k])
      }
      await api.addAnalytics(projectId, { campaign: form.campaign, metrics, notes: form.notes })
      setForm({ campaign: '', reach: '', clicks: '', spend: '', ctr: '', notes: '' })
      setToast('Results saved successfully.')
      load()
    } catch (err) { setToast('⚠ ' + err.message) }
    setBusy(false)
  }

  const getInsight = async () => {
    setBusy(true); setToast('')
    try { setInsight((await api.insight(projectId)).insight) }
    catch (e) { setToast('⚠ ' + e.message) }
    setBusy(false)
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={t('analytics')} tabIndex={-1} className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span>📈 {t('analytics')}</span>
          <button className="ap-close" aria-label="Close dialog" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <form className="analytics-form" onSubmit={add}>
            <label className="field">Campaign name <span className="field-help">Required</span>
              <input required data-dialog-focus="true" placeholder="e.g. Summer launch" value={form.campaign}
                onChange={(e) => setForm({ ...form, campaign: e.target.value })} />
            </label>
            <div className="form-grid">
              {['reach', 'clicks', 'spend', 'ctr'].map((key) => (
                <label className="field" key={key}>{t(key)}{key === 'ctr' ? ' (%)' : ''}
                  <input type="number" min="0" max={key === 'ctr' ? 100 : undefined}
                    step={['spend', 'ctr'].includes(key) ? '0.01' : '1'} value={form[key]}
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
                </label>
              ))}
            </div>
            <label className="field">{t('notes')}
              <textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </label>
            <button className="btn primary" disabled={busy}>{busy ? 'Working…' : '+ ' + t('pasteResults')}</button>
          </form>

          {toast && <div className="toast" role="status">{toast}</div>}

          <div className="analytics-table-wrap">
            <table className="cal-table"><caption className="sr-only">Campaign performance results</caption>
              <thead>
                <tr><th>Campaign</th><th>{t('reach')}</th><th>{t('clicks')}</th>
                  <th>{t('spend')}</th><th>{t('ctr')}</th><th>{t('notes')}</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>{r.campaign}</td>
                    <td>{r.metrics.reach ?? '—'}</td>
                    <td>{r.metrics.clicks ?? '—'}</td>
                    <td>{r.metrics.spend ?? '—'}</td>
                    <td>{r.metrics.ctr != null ? `${r.metrics.ctr}%` : '—'}</td>
                    <td>{r.notes}</td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={6} className="empty-hint">{t('nothingHere')}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="btn-row">
            <button className="btn primary" onClick={getInsight} disabled={busy || rows.length === 0}>
              🤖 {t('insight')}
            </button>
          </div>
          {insight && <pre className="insight-box">{insight}</pre>}
        </div>
      </div>
    </div>
  )
}
