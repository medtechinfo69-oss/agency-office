import { cloneElement, isValidElement, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronRight, CircleDashed, Inbox, LoaderCircle, X } from 'lucide-react'

export function Button({ children, variant = 'secondary', busy = false, onClick, ...props }) {
  return <button type="button" {...props} className={`a-button a-${variant} ${props.className || ''}`} title={props.title || (props.disabled ? 'Complete the required fields or obtain permission to use this action.' : undefined)} disabled={props.disabled || busy} aria-busy={busy} onClick={onClick}>{busy && <LoaderCircle className="a-spin" size={16} />}{children}</button>
}
export function Action({ children, onClick, onError, success, notify, ...props }) {
  const [busy, setBusy] = useState(false)
  return <Button {...props} busy={busy} onClick={async () => {
    if (busy) return
    setBusy(true)
    try { await onClick(); if (success) notify?.(success, 'success') }
    catch (error) { onError?.(error.message); notify?.(error.message, 'error') }
    finally { setBusy(false) }
  }}>{children}</Button>
}
export function Badge({ children, tone = 'neutral' }) { return <span className={`a-badge a-tone-${tone}`}><span />{children}</span> }
export function Card({ title, description, action, children, className = '' }) {
  return <section className={`a-card ${className}`}>{(title || action) && <div className="a-card-head"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>}{children}</section>
}
export function Field({ label, error, hint, children }) {
  const id = useId()
  const control = isValidElement(children) ? cloneElement(children, { 'aria-label': children.props['aria-label'] || label, 'aria-invalid': !!error, 'aria-describedby': error || hint ? id : undefined }) : children
  return <label className="a-field"><span>{label}</span>{control}{error ? <small id={id} className="a-error" role="alert">{error}</small> : hint && <small id={id}>{hint}</small>}</label>
}
export function Switch({ checked, onChange, label, disabled }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} className={`a-switch ${checked ? 'on' : ''}`} onClick={() => onChange(!checked)}><span /></button>
}
export function Empty({ title, description, action, Icon = Inbox }) {
  return <div className="a-empty"><span className="a-empty-icon"><Icon size={24} /></span><h3>{title}</h3><p>{description}</p>{action}</div>
}
export function Skeleton() { return <div className="a-skeleton-grid" role="status" aria-label="Loading settings">{Array.from({ length: 4 }, (_, i) => <div className="a-skeleton" key={i}><CircleDashed size={20} /><span /><span /></div>)}</div> }
export function Modal({ title, children, onClose }) {
  const ref = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    const dialog = ref.current
    dialog.showModal()
    return () => { dialog.close(); previous?.focus() }
  }, [])
  return createPortal(<dialog ref={ref} className="a-dialog" onCancel={(e) => { e.preventDefault(); onClose() }} onClick={(e) => { if (e.target === e.currentTarget) onClose() }}><div className="a-dialog-head"><h2>{title}</h2><Button variant="ghost" onClick={onClose} aria-label="Close dialog"><X size={18} /></Button></div>{children}</dialog>, document.body)
}
export function Confirm({ title, description, label = 'Confirm', onConfirm, onClose, notify }) {
  return <Modal title={title} onClose={onClose}><p className="a-dialog-description">{description}</p><div className="a-dialog-actions"><Button onClick={onClose}>Cancel</Button><Action variant="danger" notify={notify} onClick={async () => { await onConfirm(); onClose() }}>{label}</Action></div></Modal>
}
export function PageHeader({ title, description, action }) { return <div className="a-page-head"><div><div className="a-eyebrow">Workspace settings <ChevronRight size={12} /> {title}</div><h1>{title}</h1><p>{description}</p></div>{action}</div> }
export function InlineNotice({ children, tone = 'neutral' }) { return <div className={`a-notice a-notice-${tone}`}>{children}</div> }
export function CheckIcon() { return <Check size={16} /> }
