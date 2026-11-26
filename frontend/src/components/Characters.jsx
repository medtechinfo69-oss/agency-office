/* ============================================================
   Original clay / vinyl-toy robot characters (hand-drawn SVG).
   Manager = headphones + ID badge · Designer = cat-bot ·
   Developer = tracked riveted robot · shop extras.
   Every character is vector → crisp at 1x and 2x, transparent.
   ============================================================ */

const CREAM = '#f6f2e9'
const CREAM_D = '#e6dfd0'
const DARK = '#171b26'
const INDIGO = '#4f46e5'

/* soft clay body + glossy face screen shared by every variant */
function BaseBody({ accent = INDIGO, children, body = CREAM }) {
  return (
    <>
      {/* soft ground shadow */}
      <ellipse cx="32" cy="58" rx="17" ry="4" fill="rgba(0,0,0,.14)" />
      {/* body */}
      <rect x="14" y="24" width="36" height="30" rx="14" fill={body}
        stroke="rgba(0,0,0,.08)" />
      <rect x="14" y="24" width="36" height="14" rx="12" fill="#ffffff" opacity=".35" />
      {/* belly seam */}
      <path d="M22 46 Q32 51 42 46" stroke={CREAM_D} strokeWidth="2" fill="none"
        strokeLinecap="round" />
      {/* face screen */}
      <rect x="19" y="28" width="26" height="16" rx="8" fill={DARK} />
      <rect x="21" y="30" width="22" height="6" rx="3" fill="#ffffff" opacity=".08" />
      {/* eyes + smile (glow) */}
      <circle cx="27" cy="35" r="2.6" fill={accent}>
        <animate attributeName="opacity" values="1;1;.35;1" dur="4s" repeatCount="indefinite" />
      </circle>
      <circle cx="37" cy="35" r="2.6" fill={accent}>
        <animate attributeName="opacity" values="1;.35;1;1" dur="4s" repeatCount="indefinite" />
      </circle>
      <path d="M28 39.5 Q32 42.5 36 39.5" stroke={accent} strokeWidth="1.6"
        fill="none" strokeLinecap="round" />
      {/* antenna */}
      <line x1="32" y1="24" x2="32" y2="16" stroke={CREAM_D} strokeWidth="2.4" />
      <circle cx="32" cy="14" r="3" fill={accent} />
      {children}
    </>
  )
}

/* ---------- Manager: Nora — headphones + ID badge ---------- */
export function ManagerBot({ size = 64, color = INDIGO }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Manager robot">
      <BaseBody accent={color}>
        {/* headphones */}
        <path d="M17 32 Q17 16 32 16 Q47 16 47 32" stroke={color} strokeWidth="3.4"
          fill="none" strokeLinecap="round" />
        <rect x="12" y="30" width="7" height="11" rx="3.5" fill={color} />
        <rect x="45" y="30" width="7" height="11" rx="3.5" fill={color} />
        {/* ID badge */}
        <rect x="34" y="46" width="12" height="8" rx="2" fill="#fff"
          stroke={CREAM_D} />
        <rect x="36" y="48" width="5" height="4" rx="1" fill={color} opacity=".8" />
        <line x1="43" y1="48.5" x2="44.5" y2="48.5" stroke="#9aa1ad" strokeWidth="1.2" />
        <line x1="43" y1="51" x2="44.5" y2="51" stroke="#9aa1ad" strokeWidth="1.2" />
      </BaseBody>
    </svg>
  )
}

/* ---------- Designer: Lina — friendly cat-bot ---------- */
export function DesignerBot({ size = 64, color = '#ec4899' }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Designer cat robot">
      <BaseBody accent={color}>
        {/* ears */}
        <path d="M17 26 L15 14 L26 21 Z" fill={CREAM} stroke="rgba(0,0,0,.08)" />
        <path d="M18.5 24 L17.5 17.5 L23.5 21 Z" fill={color} opacity=".85" />
        <path d="M47 26 L49 14 L38 21 Z" fill={CREAM} stroke="rgba(0,0,0,.08)" />
        <path d="M45.5 24 L46.5 17.5 L40.5 21 Z" fill={color} opacity=".85" />
        {/* whiskers */}
        <path d="M14 37 L9 35 M14 40 L9 41" stroke={CREAM_D} strokeWidth="1.4" strokeLinecap="round" />
        <path d="M50 37 L55 35 M50 40 L55 41" stroke={CREAM_D} strokeWidth="1.4" strokeLinecap="round" />
        {/* tail */}
        <path d="M48 52 Q58 50 56 40" stroke={CREAM} strokeWidth="5" fill="none" strokeLinecap="round" />
        <path d="M48 52 Q58 50 56 40" stroke={color} strokeWidth="2" fill="none"
          strokeLinecap="round" strokeDasharray="3 4" />
      </BaseBody>
    </svg>
  )
}

/* ---------- Developer: Karim — tracked, riveted robot ---------- */
export function DeveloperBot({ size = 64, color = '#22c55e' }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Developer tracked robot">
      <BaseBody accent={color}>
        {/* rivets */}
        {[[18, 30], [46, 30], [18, 46], [46, 46]].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="1.4" fill={CREAM_D} />
        ))}
        {/* visor bolt */}
        <rect x="24" y="24.5" width="16" height="3" rx="1.5" fill={CREAM_D} />
        {/* tracks */}
        <rect x="13" y="50" width="38" height="9" rx="4.5" fill="#3a4150" />
        {[17, 24, 31, 38, 45].map((x) => (
          <circle key={x} cx={x} cy="54.5" r="2.4" fill="#242a36" stroke="#4b5563" strokeWidth="1" />
        ))}
      </BaseBody>
    </svg>
  )
}

/* ---------- shop extras ---------- */
export function OwlBot({ size = 64, color = '#a78bfa' }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Owl robot">
      <BaseBody accent={color} body="#efe8ff">
        <path d="M16 28 Q20 20 26 24 M48 28 Q44 20 38 24" stroke={color} strokeWidth="2.4"
          fill="none" strokeLinecap="round" />
        <path d="M20 50 Q32 58 44 50" stroke="#d9ccfb" strokeWidth="3" fill="none" strokeLinecap="round" />
      </BaseBody>
    </svg>
  )
}

export function PenguinBot({ size = 64, color = '#38bdf8' }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Penguin robot">
      <ellipse cx="32" cy="58" rx="15" ry="3.6" fill="rgba(0,0,0,.14)" />
      <rect x="15" y="22" width="34" height="34" rx="15" fill="#20293a" />
      <rect x="21" y="32" width="22" height="22" rx="10" fill={CREAM} />
      <rect x="21" y="27" width="22" height="12" rx="6" fill={DARK} />
      <circle cx="27.5" cy="33" r="2.4" fill={color} />
      <circle cx="36.5" cy="33" r="2.4" fill={color} />
      <path d="M30 37 L34 37 L32 40 Z" fill="#f59e0b" />
      <path d="M15 40 Q9 46 13 52 M49 40 Q55 46 51 52" stroke="#20293a" strokeWidth="5"
        fill="none" strokeLinecap="round" />
    </svg>
  )
}

export function BlobBot({ size = 64, color = '#f59e0b' }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Blob robot">
      <ellipse cx="32" cy="58" rx="16" ry="3.6" fill="rgba(0,0,0,.14)" />
      <path d="M14 46 Q12 24 32 22 Q52 24 50 46 Q46 54 32 54 Q18 54 14 46 Z"
        fill={color} opacity=".9" />
      <ellipse cx="32" cy="34" rx="13" ry="8" fill={DARK} />
      <circle cx="27" cy="34" r="2.6" fill="#fff" />
      <circle cx="37" cy="34" r="2.6" fill="#fff" />
      <path d="M28 39 Q32 42 36 39" stroke="#fff" strokeWidth="1.6" fill="none" strokeLinecap="round" />
    </svg>
  )
}

export function AstronautBot({ size = 64, color = INDIGO }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Astronaut robot">
      <BaseBody accent={color}>
        <rect x="12" y="24" width="40" height="18" rx="9" fill="#e8ecf4" opacity=".0" />
        <path d="M15 30 Q15 14 32 14 Q49 14 49 30" stroke="#e8ecf4" strokeWidth="3" fill="none" />
        <rect x="44" y="44" width="10" height="7" rx="2" fill="#e8ecf4" />
        <circle cx="49" cy="47.5" r="1.6" fill={color} />
      </BaseBody>
    </svg>
  )
}

export function RoundBot({ size = 64, color = '#14b8a6' }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Tiny round robot">
      <ellipse cx="32" cy="58" rx="14" ry="3.4" fill="rgba(0,0,0,.14)" />
      <circle cx="32" cy="40" r="18" fill={CREAM} stroke="rgba(0,0,0,.08)" />
      <circle cx="32" cy="40" r="18" fill="#fff" opacity=".25" />
      <rect x="21" y="33" width="22" height="13" rx="6.5" fill={DARK} />
      <circle cx="27.5" cy="39.5" r="2.5" fill={color} />
      <circle cx="36.5" cy="39.5" r="2.5" fill={color} />
      <line x1="32" y1="22" x2="32" y2="16" stroke={CREAM_D} strokeWidth="2.4" />
      <circle cx="32" cy="14" r="3" fill={color} />
    </svg>
  )
}

const VARIANTS = {
  manager: ManagerBot,
  designer: DesignerBot,
  developer: DeveloperBot,
  owl: OwlBot,
  penguin: PenguinBot,
  blob: BlobBot,
  astronaut: AstronautBot,
  round: RoundBot,
}

export const CHARACTER_IDS = ['manager', 'designer', 'developer', 'owl', 'penguin', 'blob', 'astronaut']

export const SHOP_CHARACTERS = [
  { id: 'manager', label: 'Headphone HQ', Bot: ManagerBot },
  { id: 'designer', label: 'Cat Studio', Bot: DesignerBot },
  { id: 'developer', label: 'Tread', Bot: DeveloperBot },
  { id: 'owl', label: 'Night Owl', Bot: OwlBot },
  { id: 'penguin', label: 'Cool Penguin', Bot: PenguinBot },
  { id: 'blob', label: 'Sunny Blob', Bot: BlobBot },
  { id: 'astronaut', label: 'Astro', Bot: AstronautBot },
  { id: 'round', label: 'Buddy', Bot: RoundBot },
]

/* pick a character by agent id (defaults to the round bot) */
export function AgentBot({ agentId, size = 64, color }) {
  const key = { nora: 'manager', lina: 'designer', karim: 'developer' }[agentId] || 'round'
  const Bot = VARIANTS[key] || RoundBot
  return <Bot size={size} color={color} />
}

export default VARIANTS
