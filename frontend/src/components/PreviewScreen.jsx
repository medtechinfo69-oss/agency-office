import useDialog from './useDialog'
import { useEffect, useState } from 'react'
import { api } from '../api'

/* Preview: deliverables shown as Facebook / Instagram post & ad mockups */
export default function PreviewScreen({ t, projectId, onClose }) {
  const dialogRef = useDialog(onClose)
  const [deliverables, setDeliverables] = useState([])
  const [meta, setMeta] = useState({ drafts: [], configured: false })
  const [busy, setBusy] = useState('')
  const [toast, setToast] = useState('')
  const [tab, setTab] = useState('posts')

  const load = async () => {
    try {
      const [d, m] = await Promise.all([
        api.deliverables(projectId),
        api.metaDrafts(projectId),
      ])
      setDeliverables(d)
      setMeta(m)
    } catch (e) {
      setToast('⚠ ' + e.message)
    }
  }

  useEffect(() => { load() }, [projectId]) // eslint-disable-line

  const run = async (fn, key) => {
    setBusy(key)
    setToast('')
    try { await fn(); setToast('Completed successfully.') } catch (e) { setToast('⚠ ' + e.message) }
    setBusy('')
    load()
  }

  const cal = deliverables.find((d) => d.kind === 'calendar')
  const camp = deliverables.find((d) => d.kind === 'campaign')
  const images = (camp?.data?.images) || []
  const variants = camp?.data?.variants || []
  const days = cal?.data?.days || []

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={t('preview')} tabIndex={-1} className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span>👁 {t('preview')} — Facebook / Instagram</span>
          <button className="ap-close" aria-label="Close dialog" onClick={onClose}>✕</button>
        </div>

        <div className="modal-toolbar">
          <button className={`btn ${tab === 'posts' ? 'primary' : ''}`} onClick={() => setTab('posts')}>
            📱 Posts & Ads
          </button>
          <button className={`btn ${tab === 'calendar' ? 'primary' : ''}`} onClick={() => setTab('calendar')}>
            🗓 {t('calendar')}
          </button>
          <button className={`btn ${tab === 'campaign' ? 'primary' : ''}`} onClick={() => setTab('campaign')}>
            📣 {t('campaigns')}
          </button>
          <span className="spacer" />
          <button className="btn" disabled={!!busy}
            onClick={() => run(() => api.campaign(projectId), 'camp')}>
            {busy === 'camp' ? t('running') : `⚡ ${t('generate')} ${t('campaigns')}`}
          </button>
          <button className="btn" disabled={!!busy}
            onClick={() => run(() => api.calendar(projectId, 30), 'cal')}>
            {busy === 'cal' ? t('running') : `⚡ ${t('generate')} ${t('calendar')}`}
          </button>
          <a className="btn good" href={api.exportZip(projectId)} target="_blank" rel="noreferrer">
            ⬇ {t('export')}
          </a>
        </div>

        {toast && <div className="toast" role="status">{toast}</div>}

        <div className="modal-body">
          {tab === 'posts' && (
            <div className="mock-grid">
              {images.length === 0 && variants.length === 0 && (
                <div className="empty-hint">Generate a campaign first — Zed will create the visuals.</div>
              )}
              {variants.map((v, i) => {
                const img = images.find((im) => im.label === v.label && im.ratio === '1:1')
                  || images[i * 2]
                return (
                  <div key={v.label} className="mock-col">
                    <div className="mock-label">Variant {v.label} · Facebook feed</div>
                    <div className="fb-post">
                      <div className="fb-head">
                        <div className="fb-pfp">SL</div>
                        <div>
                          <b>SecureLife Insurance</b>
                          <div className="fb-sub">Sponsored · 🌐</div>
                        </div>
                        <span className="fb-dots">⋯</span>
                      </div>
                      <div className="fb-caption">{v.primary_text}</div>
                      {img && <img className="fb-img" src={img.url} alt="" />}
                      <div className="fb-link">
                        <div className="fb-link-domain">SECURELIFE.COM</div>
                        <div className="fb-link-title">{v.headline}</div>
                        <div className="fb-link-desc">Free 15-min consultation with a licensed advisor.</div>
                      </div>
                      <button className="fb-cta">{v.cta}</button>
                      <div className="fb-actions">👍 Like · 💬 Comment · ↗ Share</div>
                    </div>

                    <div className="mock-label">Instagram · 4:5</div>
                    <div className="ig-post">
                      <div className="ig-head">
                        <div className="ig-pfp" />
                        <b>securelife</b>
                        <span className="ig-more">⋯</span>
                      </div>
                      {(() => {
                        const ig = images.find((im) => im.label === v.label && im.ratio === '4:5')
                        return ig ? <img className="ig-img" src={ig.url} alt="" /> :
                          <div className="ig-img placeholder">4:5 creative</div>
                      })()}
                      <div className="ig-actions">🤍 💬 ↗ · 🔖</div>
                      <div className="ig-caption"><b>securelife</b> {v.primary_text}</div>
                      <button className="ig-cta">{v.cta} →</button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {tab === 'calendar' && (
            <div className="analytics-table-wrap">
              {days.length === 0 && <div className="empty-hint">Generate the calendar first.</div>}
              <table className="cal-table">
                <thead>
                  <tr>
                    <th>#</th><th>Ch</th><th>Format</th><th>Theme</th>
                    <th>Caption</th><th>Hashtags</th><th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {days.map((d) => (
                    <tr key={d.day}>
                      <td>{d.day}</td>
                      <td>{d.channel}</td>
                      <td>{d.format}</td>
                      <td>{d.theme}</td>
                      <td className="cap">{d.caption}</td>
                      <td className="tags">{(d.hashtags || []).join(' ')}</td>
                      <td>{d.best_time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tab === 'campaign' && (
            <div>
              {!camp && <div className="empty-hint">Generate the campaign first.</div>}
              {camp && (
                <div className="campaign-view">
                  <div className="camp-grid">
                    <div className="camp-card"><b>Objective</b><div>{camp.data.objective}</div></div>
                    <div className="camp-card"><b>Audience</b>
                      <div>{camp.data.audience?.age} · {camp.data.audience?.location}</div>
                      <div className="dim">{camp.data.audience?.interests}</div>
                      <div className="dim">{(camp.data.audience?.placements || []).join(' · ')}</div>
                    </div>
                    <div className="camp-card"><b>Budget</b>
                      <div>{typeof camp.data.budget_plan?.daily === 'string' ? camp.data.budget_plan.daily : '—'}</div>
                      <div className="dim">{camp.data.budget_plan?.note}</div>
                    </div>
                    <div className="camp-card"><b>KPIs</b>
                      {(camp.data.kpi || []).map((k) => <div key={k}>▸ {k}</div>)}
                    </div>
                  </div>

                  <h3 className="sec">{t('compliance')}
                    {' '}
                    {camp.data.compliance_report ? (
                      <span className={`chip ${camp.data.compliance_report.passed ? 'good' : 'bad'}`}>
                        {camp.data.compliance_report.passed ? t('passed') : t('issues')}
                      </span>
                    ) : (
                      <span className="chip">—</span>
                    )}
                  </h3>
                  <div className="issues">
                    {(camp.data.compliance_report?.issues || []).map((iss, i) => (
                      <div key={i} className={`issue sev-${iss.severity}`}>
                        <b>[{iss.severity}]</b> {iss.where} — {iss.message}
                        {iss.snippet && <em> “{iss.snippet}”</em>}
                      </div>
                    ))}
                    {(camp.data.compliance_report?.issues || []).length === 0 && (
                      <div className="good">No compliance issues found.</div>
                    )}
                  </div>

                  <h3 className="sec">Meta drafts <span className="dim">({meta.configured ? 'Graph API ON' : 'local only — set META_* in .env to publish'})</span></h3>
                  {meta.drafts.map((d) => (
                    <div key={d.id} className="draft-row">
                      <span className={`chip ${d.status}`}>{d.status}</span>
                      <span>{d.payload.headline || d.payload.kind}</span>
                      <span className="spacer" />
                      <button className="btn good" disabled={!d.payload}
                        onClick={() => run(() => api.publishDraft(projectId, d.id), d.id)}>
                        ✔ Approve & publish
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
