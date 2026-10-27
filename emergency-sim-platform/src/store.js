/** 全局状态（轻量 reactive store；大体量结果用 shallowRef 避免深度响应开销） */
import { reactive, shallowRef, computed } from 'vue'
import { STAGES, SITES, WIND_PRESETS, paramsFromPresets, assessResilience } from './engine/index.js'
import { runSimulationService, loadStaticData } from './services/simService.js'

const cfg = () => window.EMERGENCY_SIM_CONFIG || {}

export const state = reactive({
  params: paramsFromPresets({ siteId: 'taihe', windPresetId: 'sw2' }),
  running: false,
  error: null,
  stages: STAGES.map((s) => ({ ...s, status: 'pending', ms: null, summary: '' })),
  logs: [],
  processOpen: false,
  view: 'overview', // overview | hazard | supply | evac
  supplyScheme: 'coordinated',
  evacScheme: 'all',
  pickMode: false,
  leftCollapsed: false,
  rightCollapsed: false,
  playback: { t: 180, playing: false, speed: 4 },
  advancedOpen: false,
  detailOpen: false,
  ready: false,
  runCount: 0,
})

export const result = shallowRef(null)
export const staticData = shallowRef(null)

export const resilience = computed(() =>
  result.value ? assessResilience(result.value, state.supplyScheme, state.evacScheme) : null,
)

export const progress = computed(() => {
  const done = state.stages.filter((s) => s.status === 'done' || s.status === 'skipped').length
  const running = state.stages.some((s) => s.status === 'running') ? 0.5 : 0
  return Math.min(1, (done + running) / state.stages.length)
})

export const SITE_OPTIONS = [...SITES.map((s) => ({ value: s.id, label: s.name, desc: s.desc })), { value: 'custom', label: '地图选点', desc: '在地图上点击选择事故位置' }]
export const WIND_OPTIONS = WIND_PRESETS.map((w) => ({ value: w.id, label: w.name, desc: `${w.speed} m/s · ${w.stability}类 · ${w.note}` }))
export const METHOD_OPTIONS = [
  { value: 'dual', label: '双链协同优化', desc: '疏散 → 就地避难需求 → 物资配送' },
  { value: 'evac', label: '人员疏散优化', desc: '仅多类型人员疏散' },
  { value: 'supply', label: '物资配送优化', desc: '仅现场救援物资配送' },
]
export const ALGORITHM_OPTIONS = [
  { value: 'two_stage', label: '两阶段求解算法', desc: '贪心构造 + 2-opt 局部搜索（论文）' },
  { value: 'two_stage_direct', label: '两阶段·直送优先', desc: '论文 5.3 节改进：直送超时窗/封闭区内才接力' },
  { value: 'greedy', label: '贪心构造算法', desc: '仅第一阶段' },
]
export const SOLVER_OPTIONS = [
  { value: 'local', label: '内置求解器', desc: '浏览器 Web Worker 本地计算' },
  { value: 'remote', label: '服务端求解器', desc: 'REST API（server/index.js）' },
]
export const VIEW_OPTIONS = [
  { value: 'overview', label: '综合态势' },
  { value: 'hazard', label: '灾害场景' },
  { value: 'supply', label: '物资配送' },
  { value: 'evac', label: '人员疏散' },
]

export function setSite(id) {
  if (id === 'custom') {
    state.pickMode = true
    return
  }
  state.pickMode = false
  const p = paramsFromPresets({ siteId: id }, state.params)
  state.params.siteId = p.siteId
  state.params.incident = p.incident
}

export function setIncidentFromMap(lon, lat) {
  state.params.siteId = 'custom'
  state.params.incident = { lon: +lon.toFixed(6), lat: +lat.toFixed(6), name: `自定义点(${lon.toFixed(3)},${lat.toFixed(3)})` }
  state.pickMode = false
}

export function setWind(id) {
  const w = WIND_PRESETS.find((x) => x.id === id)
  if (!w) return
  state.params.windPresetId = w.id
  state.params.windSpeed = w.speed
  state.params.windDir = w.dir
  state.params.stability = w.stability
}

export async function init() {
  staticData.value = await loadStaticData()
  state.ready = true
  if (cfg().autoRun !== false) run()
}

export async function run() {
  if (state.running) return
  state.running = true
  state.error = null
  state.processOpen = true
  state.logs = []
  state.stages.forEach((s) => { s.status = 'pending'; s.ms = null; s.summary = '' })
  state.playback.playing = false
  const params = JSON.parse(JSON.stringify(state.params))
  params.stageDelayMs = cfg().stageDelayMs ?? 450
  try {
    const res = await runSimulationService(params, {
      onStage: (e) => {
        const s = state.stages.find((x) => x.id === e.stage)
        if (!s) return
        s.status = e.status
        if (e.ms !== undefined) s.ms = e.ms
        if (e.summary) s.summary = e.summary
      },
      onLog: (e) => state.logs.push(e),
    })
    result.value = Object.freeze(res)
    state.runCount++
    if (!res.supply) state.supplyScheme = 'coordinated'
    state.playback.t = 0
    state.playback.playing = true
    notifyParent('emergency-sim:result', summarize(res))
    setTimeout(() => { if (!state.running) state.processOpen = false }, 2200)
  } catch (e) {
    state.error = e.message || String(e)
    state.logs.push({ t: 0, msg: `计算失败：${state.error}`, level: 'error' })
  } finally {
    state.running = false
  }
}

export function reset() {
  state.params = paramsFromPresets({ siteId: 'taihe', windPresetId: 'sw2' })
  state.supplyScheme = 'coordinated'
  state.evacScheme = 'all'
  state.view = 'overview'
  run()
}

/** 供 iframe 父页面使用的结果摘要 */
export function summarize(res) {
  return {
    incident: res.params.incident,
    wind: res.scenario.wind,
    evacDemand: res.zones.evacDemand,
    shelterInPlace: res.zones.shelterInPlaceTotal,
    evacuation: res.evacuation && Object.fromEntries(Object.entries(res.evacuation.schemes).map(([k, v]) => [k, { label: v.label, rate: v.rate, evacuated: v.evacuated, totalRisk: v.totalRisk }])),
    supply: res.supply && Object.fromEntries(Object.entries(res.supply.schemes).map(([k, v]) => [k, { label: v.label, completed: v.completed, total: v.totalTasks, makespan: v.makespan }])),
    resilience: res.resilience.radar.map((r) => ({ name: r.name, value: r.value })),
    elapsedMs: res.elapsedMs,
  }
}

export function notifyParent(type, payload) {
  if (window.parent && window.parent !== window) window.parent.postMessage({ type, payload }, '*')
}
