import { createApp } from 'vue'
import App from './App.vue'
import './styles/theme.css'
import { state, run, result, summarize, notifyParent, setSite, setWind } from './store.js'

createApp(App).mount('#app')

/**
 * iframe 嵌入通信（postMessage）
 *   父页面 → 本页面：
 *     { type: 'emergency-sim:run', params?: {...} }        合并参数并计算
 *     { type: 'emergency-sim:set', siteId?, windPresetId?, view? }
 *     { type: 'emergency-sim:getResult' }
 *   本页面 → 父页面：
 *     { type: 'emergency-sim:ready' }
 *     { type: 'emergency-sim:result', payload: 摘要 }       每次计算完成
 */
window.addEventListener('message', (ev) => {
  const m = ev.data
  if (!m || typeof m !== 'object' || typeof m.type !== 'string' || !m.type.startsWith('emergency-sim:')) return
  if (m.type === 'emergency-sim:run') {
    if (m.params && typeof m.params === 'object') Object.assign(state.params, m.params)
    run()
  } else if (m.type === 'emergency-sim:set') {
    if (m.siteId) setSite(m.siteId)
    if (m.windPresetId) setWind(m.windPresetId)
    if (m.view) state.view = m.view
  } else if (m.type === 'emergency-sim:getResult' && result.value) {
    notifyParent('emergency-sim:result', summarize(result.value))
  }
})
notifyParent('emergency-sim:ready', {})
