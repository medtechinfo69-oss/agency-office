import { useSyncExternalStore } from 'react'
import { api } from './api'
let state = { selection: { provider: '', model: '', image_model: '' }, providers: [], loading: false, error: '' }
const listeners = new Set()
let pending
function publish(patch) { state = { ...state, ...patch }; listeners.forEach((fn) => fn()) }
export function useModels() { return useSyncExternalStore((fn) => { listeners.add(fn); return () => listeners.delete(fn) }, () => state) }
export async function loadModels(refresh = false) {
  if (pending) return pending
  publish({ loading: true })
  pending = api.get('/models' + (refresh ? '?refresh_catalog=true' : '')).then((data) => { publish({ ...data, loading: false, error: '' }); return data }).catch((e) => { publish({ loading: false, error: e.message }); throw e }).finally(() => { pending = null })
  return pending
}
export async function selectModel(provider, model, image_model) {
  const selection = await api.put('/models/selection', { provider, model, ...(image_model ? { image_model } : {}) })
  publish({ selection })
  window.dispatchEvent(new Event('agency:model-changed'))
  return selection
}
export function notifyModelChange() { return loadModels().then(() => window.dispatchEvent(new Event('agency:model-changed'))) }
