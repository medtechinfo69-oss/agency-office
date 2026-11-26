import { useEffect, useState } from 'react'
import { api } from '../api'

/* New project dialog — template chips, clean form, single action row */
export default function NewProjectModal({ t, onClose, onCreate }) {
  const [templates, setTemplates] = useState([])
  const [name, setName] = useState('')
  const [brief, setBrief] = useState('')
  const [template, setTemplate] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => { api.templates().then(setTemplates).catch(() => {}) }, [])

  const ready = brief.trim() || template

  const submit = async (e) => {
    e.preventDefault()
    if (!ready) {
      setErr('Write a brief or pick a template to continue.')
      return
    }
    setBusy(true); setErr('')
    try {
      await onCreate({ name: name.trim() || 'Untitled project', brief: brief.trim(), template })
    } catch (e2) {
      setErr(e2.message)
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal np-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="np-title">
            <span className="np-icon" aria-hidden="true">🆕</span>
            <div className="np-heading">
              <div className="np-h">{t('newProject')}</div>
              <div className="np-sub">Nora turns your brief into a plan — you approve before any work starts</div>
            </div>
          </div>
          <button className="ap-close" onClick={onClose} aria-label="close">✕</button>
        </div>

        <form className="modal-body np-form" onSubmit={submit}>
          <label className="np-field">
            <span className="np-label">{t('project')} name</span>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Summer campaign"
              autoFocus />
          </label>

          <div className="np-field">
            <span className="np-label">{t('templates')}</span>
            <div className="np-chips" role="radiogroup" aria-label="templates">
              <button type="button"
                className={'np-chip' + (template ? '' : ' on')}
                onClick={() => setTemplate('')}>
                ✨ Blank
              </button>
              {templates.map((tp) => (
                <button type="button" key={tp.id}
                  className={'np-chip' + (template === tp.id ? ' on' : '')}
                  onClick={() => setTemplate(template === tp.id ? '' : tp.id)}>
                  {tp.name}
                </button>
              ))}
            </div>
          </div>

          <label className="np-field">
            <span className="np-label">{t('brief')}</span>
            <textarea rows={7} value={brief} onChange={(e) => setBrief(e.target.value)}
              placeholder="Goals, audience, deliverables, tone, hard rules…" />
            <span className="np-hint">
              {brief.trim()
                ? `${brief.trim().length} chars · Nora will split it into tasks`
                : 'What should the team build? A sentence or two is enough.'}
            </span>
          </label>

          {err && <div className="np-err">⚠ {err}</div>}

          <div className="np-footer">
            <button type="button" className="btn ghost" onClick={onClose}>{t('close')}</button>
            <button className="btn primary" disabled={busy || !ready}>
              {busy ? t('running') : `${t('create')} →`}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
