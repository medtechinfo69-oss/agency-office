import { useEffect, useState } from 'react'
import { api } from '../api'

/* Analytics dashboard: paste campaign results → agents learn what performs */
export default function AnalyticsScreen({ t, projectId, onClose }) {
  const [rows, setRows] = useState([])
  const [form, setForm] = useState({ campaign: '', reach: '', clicks: '', spend: '', ctr: '', notes: '' })
  const [insight, setInsight] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')

  const load = () => api.analytics(projectId).then(setRows).catch((e) => setToast('⚠ ' + e.message))
  useEffect(() => { load() }, [projectId]) // eslint-disable-line

  const add = async (e) => {
    e.preventDefault()
    if (!form.campaign.trim()) return
    setBusy(true)
    try {
      const metrics = {}
      for (const k of ['reach', 'clicks', 'spend', 'ctr']) {
        if (form[k] !== '') metrics[k] = Number(form[k])
      }
      await api.addAnalytics(projectId, { campaign: form.campaign, metrics, notes: form.notes })
      setForm({ campaign: '', reach: '', clicks: '', spend: '', ctr: '', notes: '' })
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
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span>📈 {t('analytics')}</span>
          <button className="ap-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <form className="analytics-form" onSubmit={add}>
            <input placeholder="Campaign name *" value={form.campaign}
              onChange={(e) => setForm({ ...form, campaign: e.target.value })} />
            <input placeholder={t('reach')} type="number" value={form.reach}
              onChange={(e) => setForm({ ...form, reach: e.target.value })} />
            <input placeholder={t('clicks')} type="number" value={form.clicks}
              onChange={(e) => setForm({ ...form, clicks: e.target.value })} />
            <input placeholder={t('spend')} type="number" step="0.01" value={form.spend}
              onChange={(e) => setForm({ ...form, spend: e.target.value })} />
            <input placeholder={t('ctr') + ' %'} type="number" step="0.01" value={form.ctr}
              onChange={(e) => setForm({ ...form, ctr: e.target.value })} />
            <input placeholder={t('notes')} value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            <button className="btn primary" disabled={busy}>+ {t('pasteResults')}</button>
          </form>

          {toast && <div className="toast">{toast}</div>}

          <div className="analytics-table-wrap">
            <table className="cal-table">
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
                    <td>{r.metrics.ctr ?? '—'}%</td>
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
