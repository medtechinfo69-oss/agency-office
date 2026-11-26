import React from 'react'
import ReactDOM from 'react-dom/client'
import { applyAppearanceOptions } from './components/AppearanceOptions'
import AuthGate from './components/AuthGate'
import '@fontsource/inter/400.css'
import '@fontsource/inter/600.css'
import './styles/theme.css'
import './styles/app.css'
import './styles/admin.css'
const root = document.documentElement
root.classList.add(localStorage.getItem('ao_theme') === 'day' ? 'theme-light' : 'theme-dark')
root.dataset.accent = localStorage.getItem('ao_accent') || 'indigo'
root.dataset.density = localStorage.getItem('ao_density') || 'comfortable'
applyAppearanceOptions()
new MutationObserver(applyAppearanceOptions).observe(root, { attributes: true, attributeFilter: ['class'] })

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthGate />
  </React.StrictMode>,
)
