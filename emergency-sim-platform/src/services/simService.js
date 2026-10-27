/**
 * 求解服务适配层
 *   local  —— 浏览器 Web Worker 内运行引擎（默认，无需后端）
 *   remote —— 调用服务端 REST API（server/index.js），NDJSON 流式回传进度
 * 两种方式回调一致：onStage / onLog，最终 resolve(result)。
 */
const cfg = () => window.EMERGENCY_SIM_CONFIG || {}

let worker = null
let seq = 0

function dataBaseUrl() {
  return new URL(cfg().dataBase || './data/', window.location.href).href
}

export function runLocal(params, { onStage, onLog } = {}) {
  if (!worker) worker = new Worker(new URL('../workers/sim.worker.js', import.meta.url), { type: 'module' })
  const id = ++seq
  return new Promise((resolve, reject) => {
    const handler = (ev) => {
      const m = ev.data
      if (!m || m.id !== id) return
      if (m.type === 'stage') onStage?.(m.payload)
      else if (m.type === 'log') onLog?.(m.payload)
      else if (m.type === 'result') { worker.removeEventListener('message', handler); resolve(m.result) }
      else if (m.type === 'error') { worker.removeEventListener('message', handler); reject(new Error(m.message)) }
    }
    worker.addEventListener('message', handler)
    worker.postMessage({ type: 'run', id, params: JSON.parse(JSON.stringify(params)), dataBase: dataBaseUrl() })
  })
}

export async function runRemote(params, { onStage, onLog } = {}) {
  const base = (cfg().apiBase || '').replace(/\/$/, '')
  const resp = await fetch(`${base}/api/emergency/simulate?stream=1`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ params }),
  })
  if (!resp.ok || !resp.body) throw new Error(`服务端求解失败：HTTP ${resp.status}`)
  const reader = resp.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  let result = null
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let nl
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim()
      buf = buf.slice(nl + 1)
      if (!line) continue
      const m = JSON.parse(line)
      if (m.type === 'stage') onStage?.(m.payload)
      else if (m.type === 'log') onLog?.(m.payload)
      else if (m.type === 'result') result = m.result
      else if (m.type === 'error') throw new Error(m.message)
    }
  }
  if (!result) throw new Error('服务端未返回结果')
  return result
}

export function runSimulationService(params, hooks) {
  return params.solver === 'remote' ? runRemote(params, hooks) : runLocal(params, hooks)
}

export async function loadStaticData() {
  const base = dataBaseUrl()
  const get = async (f) => {
    const r = await fetch(new URL(f, base))
    if (!r.ok) throw new Error(`${f}: ${r.status}`)
    return r.json()
  }
  const [boundary, reference, facilities] = await Promise.all([
    get('yizhuang_boundary.geojson'), get('paper_reference.json'), get('facilities.json'),
  ])
  return { boundary, reference, facilities }
}
