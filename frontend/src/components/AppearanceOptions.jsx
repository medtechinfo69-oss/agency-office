import { useState } from 'react'
import { Button, Card, Field, Switch } from './admin-ui'

function rgb(hex) { return [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)) }
function luminance(c) { return c.map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0) }
function contrast(a,b) { const [x,y]=[luminance(a),luminance(b)].sort((a,b)=>b-a);return(x+.05)/(y+.05) }
export function applyAppearanceOptions() {
 const root=document.documentElement
 root.dataset.animations=localStorage.getItem('ao_animations')||'on'
 root.dataset.sidebarStyle=localStorage.getItem('ao_sidebar_style')||'comfortable'
 const scale=Number(localStorage.getItem('ao_font_size')||14)
 root.style.setProperty('--a-md',Math.max(12,Math.min(16,scale))+'px')
 const custom=localStorage.getItem('ao_custom_accent')
 for(const name of ['--accent','--accent-hover','--accent-text','--accent-subtle','--accent-border'])root.style.removeProperty(name)
 if(!/^#[0-9a-f]{6}$/i.test(custom||''))return
 const base=rgb(custom),dark=root.classList.contains('theme-dark'),bg=dark?[20,24,33]:[255,255,255]
 let primary=[...base],text=[...base]
 for(let i=0;i<100&&contrast(primary,[255,255,255])<4.5;i++)primary=primary.map(n=>Math.round(n*.96))
 for(let i=0;i<100&&contrast(text,bg)<4.5;i++)text=text.map(n=>Math.round(dark?n+(255-n)*.05:n*.94))
 root.style.setProperty('--accent',`rgb(${primary.join(',')})`)
 root.style.setProperty('--accent-hover',`rgb(${primary.map(n=>Math.round(n*.88)).join(',')})`)
 root.style.setProperty('--accent-text',`rgb(${text.join(',')})`)
 root.style.setProperty('--accent-subtle',`rgb(${base.map((n,i)=>Math.round(n*.12+bg[i]*.88)).join(',')})`)
 root.style.setProperty('--accent-border',`rgb(${base.map((n,i)=>Math.round(n*.4+bg[i]*.6)).join(',')})`)
}
export default function AppearanceOptions({notify,setTheme}) {
 const [font,setFont]=useState(localStorage.getItem('ao_font_size')||'14'),[hex,setHex]=useState(localStorage.getItem('ao_custom_accent')||'#6366ed'),[animations,setAnimations]=useState(localStorage.getItem('ao_animations')!=='off'),[sidebar,setSidebar]=useState(localStorage.getItem('ao_sidebar_style')||'comfortable')
 const set=(key,value)=>{localStorage.setItem('ao_'+key,value);applyAppearanceOptions();notify('Appearance preference applied.','success')}
 return <Card title="Workspace presentation" description="Preferences apply to this browser. Custom accents are adjusted for readable text and buttons."><div className="a-form"><Field label="Custom accent hex" error={/^#[0-9a-f]{6}$/i.test(hex)?'':'Use a six-digit hex color.'}><input value={hex} maxLength={7} onChange={e=>setHex(e.target.value)} placeholder="#6366ed"/></Field><div className="a-actions"><Button disabled={!/^#[0-9a-f]{6}$/i.test(hex)} onClick={()=>set('custom_accent',hex)}>Apply custom accent</Button><Button onClick={()=>{localStorage.removeItem('ao_custom_accent');applyAppearanceOptions();notify('Preset accent restored.','success')}}>Use preset accent</Button></div><Field label="Interface font size"><select value={font} onChange={e=>{setFont(e.target.value);set('font_size',e.target.value)}}><option value="12">Small · 12px</option><option value="14">Default · 14px</option><option value="16">Large · 16px</option></select></Field><Field label="Sidebar spacing"><select value={sidebar} onChange={e=>{setSidebar(e.target.value);set('sidebar_style',e.target.value)}}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></Field><div className="a-toolbar"><span>Interface animations</span><Switch label="Interface animations" checked={animations} onChange={value=>{setAnimations(value);set('animations',value?'on':'off')}}/></div><Button onClick={()=>{for(const key of ['custom_accent','font_size','sidebar_style','animations','accent','density'])localStorage.removeItem('ao_'+key);document.documentElement.dataset.accent='indigo';document.documentElement.dataset.density='comfortable';setTheme('night');setFont('14');setSidebar('comfortable');setAnimations(true);setHex('#6366ed');applyAppearanceOptions();window.dispatchEvent(new Event('agency:appearance-reset'));notify('Appearance reset to dark defaults.','success')}}>Reset appearance</Button></div></Card>
}
