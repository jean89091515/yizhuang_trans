/**
 * Web Worker：在后台线程运行模拟引擎，逐阶段回传进度与日志，避免阻塞大屏渲染。
 * 消息协议：
 *   main → worker  { type: 'run', id, params, dataBase }
 *   worker → main  { type: 'stage' | 'log', id, payload } / { type: 'result', id, result } / { type: 'error', id, message }
 */
import { runSimulation } from '../engine/index.js'

let dataPromise = null
let dataBaseLoaded = null

async function loadData(base) {
  if (dataPromise && dataBaseLoaded === base) return dataPromise
  dataBaseLoaded = base
  dataPromise = (async () => {
    const get = async (f, optional = false) => {
      const r = await fetch(new URL(f, base))
      if (!r.ok) {
        if (optional) return null
        throw new Error(`数据加载失败：${f} (${r.status})`)
      }
      return r.json()
    }
    const [facilities, population, roadNetwork] = await Promise.all([
      get('facilities.json'), get('population.json'), get('road_network.json', true).catch(() => null),
    ])
    const data = { facilities, population }
    if (roadNetwork) data.roadNetwork = roadNetwork
    return data
  })()
  return dataPromise
}

self.onmessage = async (ev) => {
  const { type, id, params, dataBase } = ev.data || {}
  if (type !== 'run') return
  try {
    const data = await loadData(dataBase)
    const result = await runSimulation(params, data, {
      onStage: (payload) => self.postMessage({ type: 'stage', id, payload }),
      onLog: (payload) => self.postMessage({ type: 'log', id, payload }),
    })
    self.postMessage({ type: 'result', id, result })
  } catch (e) {
    self.postMessage({ type: 'error', id, message: e?.message || String(e) })
  }
}
