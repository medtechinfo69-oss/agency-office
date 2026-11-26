import { useEffect, useRef, useState } from 'react'
import { Building2, MessagesSquare, GitBranch, FolderKanban, ShieldCheck, ScrollText, Sparkles, HeartPulse, ShoppingBag, PanelsTopLeft, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react'
import { PLATFORM_PAGES } from '../pages/PlatformPage'
import { ADMIN_PAGES } from '../pages/SettingsPage'
import { Button } from './admin-ui'

export const NAV = [
  { id: 'office', label: 'Office', Icon: Building2 },
  { id: 'builder', label: 'Site Builder', Icon: PanelsTopLeft },
  { id: 'chat', label: 'Chat', Icon: MessagesSquare },
  { id: 'workflows', label: 'Workflows', Icon: GitBranch },
  { id: 'projects', label: 'Projects', Icon: FolderKanban },
  { id: 'permissions', label: 'Agent planning', Icon: ShieldCheck },
  { id: 'logs', label: 'Logs', Icon: ScrollText },
  { id: 'skills', label: 'Skills', Icon: Sparkles },
  { id: 'health', label: 'System health', Icon: HeartPulse },
  { id: 'shop', label: 'Agent appearance', Icon: ShoppingBag },
  ...ADMIN_PAGES.map((p) => ({ ...p, id: 'settings/' + p.id })),
]

export default function Sidebar({ page, onNavigate, mobileOpen, setMobileOpen, profile }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('ao_sidebar_collapsed') === 'true')
  const ref = useRef(null)
  useEffect(() => {
    const media = matchMedia('(max-width: 767px)')
    const update = () => { if (ref.current) ref.current.inert = media.matches && !mobileOpen }
    update(); media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [mobileOpen])
  useEffect(() => {
    if (!mobileOpen) return
    const previous = document.activeElement
    const sidebar = ref.current
    sidebar.querySelector('button')?.focus()
    const handler = (e) => {
      if (e.key === 'Escape') { setMobileOpen(false); previous?.focus() }
      if (e.key !== 'Tab') return
      const list = [...sidebar.querySelectorAll('a,button')].filter((el) => el.offsetParent !== null)
      if (e.shiftKey && document.activeElement === list[0]) { e.preventDefault(); list.at(-1)?.focus() }
      else if (!e.shiftKey && document.activeElement === list.at(-1)) { e.preventDefault(); list[0]?.focus() }
    }
    const old = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', handler)
    return () => { document.body.style.overflow = old; document.removeEventListener('keydown', handler); previous?.focus() }
  }, [mobileOpen, setMobileOpen])
  const navigate = (event, id) => { event.preventDefault(); onNavigate(id); setMobileOpen(false) }
  const items = (entries) => entries.map(({ id, label, Icon }) => <a href={'#' + id} className={`a-nav-link ${page === id || page === 'settings' && id === 'settings/connections' ? 'active' : ''}`} aria-current={page === id ? 'page' : undefined} key={id} title={collapsed ? label : undefined} aria-label={label} onClick={(e) => navigate(e, id)}><Icon size={18} strokeWidth={1.75} /><span className="a-nav-label">{label}</span></a>)
  return <>{mobileOpen && <button className="a-drawer-shade" aria-label="Close navigation overlay" onClick={() => setMobileOpen(false)} />}<aside ref={ref} id="agency-navigation" aria-label="Workspace navigation" className={`sidebar ${collapsed && !mobileOpen ? 'is-collapsed' : ''} ${mobileOpen ? 'drawer-open' : ''}`}><div className="a-brand"><span className="a-brand-mark"><LayersMark /></span><div className="a-brand-copy"><strong>Agency Office</strong><small>Workspace console</small></div><Button variant="ghost" className="a-mobile-toggle" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={18} /></Button></div><nav className="a-nav" aria-label="Main navigation">{profile?.id==='owner'&&<><div className="a-nav-group">PLATFORM</div>{items(PLATFORM_PAGES.map(([id,label])=>({id:'platform/'+id,label,Icon:Building2})))}</>}<div className="a-nav-group">Workspace</div>{items(NAV.slice(0, 5))}<div className="a-nav-group">Administration</div>{items(NAV.slice(10))}<div className="a-nav-group">Tools & resources</div>{items(NAV.slice(5, 10))}</nav><div className="a-side-foot"><Button className="a-sidebar-collapse" variant="ghost" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed} onClick={() => { localStorage.setItem('ao_sidebar_collapsed', String(!collapsed)); setCollapsed(!collapsed) }}>{collapsed ? <PanelLeftOpen size={18} /> : <><PanelLeftClose size={18} /><span>Collapse sidebar</span></>}</Button><a className="a-user-link" href="#settings/account" title="Your account" onClick={(e) => navigate(e, 'settings/account')}><span className="a-avatar">{(profile?.name || 'Workspace owner').split(' ').map((s) => s[0]).slice(0, 2).join('').toUpperCase()}</span><div className="a-user-copy"><strong>{profile?.name || 'Your workspace'}</strong><small>{profile?.role || 'Account settings'}</small></div></a></div></aside></>
}
function LayersMark() { return <Building2 size={19} strokeWidth={1.75} /> }
