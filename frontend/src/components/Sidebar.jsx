/* Left navigation sidebar — logo, nav (lavender active pill),
   bottom: theme segmented (system/sun/moon), FR/EN, user card. */
import {
  Building2, MessagesSquare, GitBranch, FolderKanban, ShieldCheck,
  ScrollText, Sparkles, HeartPulse, ShoppingBag, Settings, LogOut,
  Sun, Moon, MonitorCog, PanelsTopLeft,
} from 'lucide-react'

export const NAV = [
  { id: 'office', label: 'Office', fr: 'Bureau', Icon: Building2, q: 'What is the Manager doing right now?' },
  { id: 'builder', label: 'Site Builder', fr: 'Créateur de sites', Icon: PanelsTopLeft, q: 'What would you like to build?' },
  { id: 'chat', label: 'Chat', fr: 'Discuter', Icon: MessagesSquare, q: 'What should the team build next?' },
  { id: 'workflows', label: 'Workflows', fr: 'Flux', Icon: GitBranch, q: 'What runs on autopilot?' },
  { id: 'projects', label: 'Projects', fr: 'Projets', Icon: FolderKanban, q: 'Where is every project standing?' },
  { id: 'permissions', label: 'Permissions', fr: 'Droits', Icon: ShieldCheck, q: 'Who can do what?' },
  { id: 'logs', label: 'Logs', fr: 'Journal', Icon: ScrollText, q: 'What happened while you were away?' },
  { id: 'skills', label: 'Skills', fr: 'Compétences', Icon: Sparkles, q: 'What can the team do?' },
  { id: 'health', label: 'System health', fr: 'Santé système', Icon: HeartPulse, q: 'Is everything healthy?' },
  { id: 'shop', label: 'Shop', fr: 'Boutique', Icon: ShoppingBag, q: 'How should the crew look?' },
  { id: 'settings', label: 'Settings', fr: 'Réglages', Icon: Settings, q: 'Tune the agency to your liking.' },
]

export default function Sidebar({
  page, onNavigate, lang, onLang, theme, onTheme, t, onLogout,
}) {
  return (
    <aside className="sidebar">
      <div className="side-logo">
        <span className="side-logo-mark" aria-hidden="true">
          <Building2 size={17} />
        </span>
        <div>
          <div className="side-logo-name">AGENCY OFFICE</div>
          <div className="side-logo-tag">AI crew, one desk</div>
        </div>
      </div>

      <nav className="side-nav" aria-label="main">
        {NAV.map(({ id, label, fr, Icon }) => (
          <button
            key={id}
            className={`side-item ${page === id ? 'active' : ''}`}
            onClick={() => onNavigate(id)}
            aria-current={page === id ? 'page' : undefined}
          >
            <Icon size={16} strokeWidth={1.9} />
            <span>{lang === 'fr' ? fr : label}</span>
          </button>
        ))}
      </nav>

      <div className="side-foot">
        {/* theme segmented: system / sun / moon */}
        <div className="seg theme-seg" role="radiogroup" aria-label="theme">
          <button className={theme === 'auto' ? 'on' : ''} title="System"
            onClick={() => onTheme('auto')} aria-pressed={theme === 'auto'}>
            <MonitorCog size={14} />
          </button>
          <button className={theme === 'day' ? 'on' : ''} title="Day"
            onClick={() => onTheme('day')} aria-pressed={theme === 'day'}>
            <Sun size={14} />
          </button>
          <button className={theme === 'night' ? 'on' : ''} title="Night"
            onClick={() => onTheme('night')} aria-pressed={theme === 'night'}>
            <Moon size={14} />
          </button>
        </div>

        {/* FR / EN */}
        <select
          className="lang-pick"
          value={lang}
          onChange={(e) => onLang(e.target.value)}
          aria-label="language"
        >
          <option value="en">EN</option>
          <option value="fr">FR</option>
        </select>

        {/* user card */}
        <div className="user-card">
          <span className="user-avatar" aria-hidden="true">BO</span>
          <div className="user-meta">
            <div className="user-name">Boss</div>
            <div className="user-role">{t('agencyOwner') || 'Agency owner'}</div>
          </div>
          <button className="user-out" title="Log out" onClick={onLogout}>
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </aside>
  )
}
