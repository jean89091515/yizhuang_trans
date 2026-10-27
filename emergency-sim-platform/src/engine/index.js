/**
 * 重大突发事件（危险品泄漏）交通应急模拟引擎 —— 计算流程编排
 *
 *   场景构建 → 高斯烟羽扩散 → ERPG 分区与人口 → 路网损伤 → 人员疏散优化 → 物资配送优化 → 韧性评估
 *
 * 纯 JS（ES Module），浏览器（Web Worker）与 Node.js 服务端通用，无 DOM 依赖。
 *
 * 用法:
 *   import { runSimulation } from './engine/index.js'
 *   const result = await runSimulation(params, { facilities, population, roadNetwork }, { onStage, onLog })
 */
import {
  DEFAULT_PARAMS, ENGINE_VERSION, GAS_THRESHOLDS, ZONE_KEYS, ZONE_NAMES, POP_CLASSES, VEHICLE_MODES, MODE_KEYS,
  SUPPLY_CATEGORIES, mergeParams, beaufort, windDirName,
} from './defaults.js'
import { computePlume, plumeContours, plumeRaster } from './plume.js'
import { computeZones, zonePolygons, loadPopulation, aggregatePopulation } from './zones.js'
import { TravelModel, RoadGraph, TAIHE_ROAD_PROFILE_KM } from './travel.js'
import { buildOrigins, buildDestinations, fleetConfig, runEvacScheme } from './evacuation.js'
import { buildLogistics, buildTasks, SupplySolver, summarizeSupply, serializeSchedule } from './supply.js'
import { distM } from './geo.js'

export * from './defaults.js'
export { wgs84ToGcj02, gcj02ToWgs84 } from './geo.js'

export const STAGES = [
  { id: 'scene', name: '场景构建', short: '场景构建', desc: '事故点、气象、危化品与应急资源加载' },
  { id: 'plume', name: '高斯烟羽扩散模拟', short: '烟羽扩散', desc: 'Briggs 城市扩散参数，逐网格计算地面浓度' },
  { id: 'zones', name: 'ERPG 危险分区', short: '危险分区', desc: '三级分区 + 地块人口统计 + 疏散/就地避难划分' },
  { id: 'roads', name: '路网损伤评估', short: '路网损伤', desc: '道路封闭 + BPR 拥堵，构建受损路网行程时间' },
  { id: 'evac', name: '多类型人员疏散优化', short: '人员疏散', desc: '风险感知时间步进调度，5 方案 + 救护车敏感性' },
  { id: 'supply', name: '应急物资配送优化', short: '物资配送', desc: '货车—无人机协同，贪心构造 + 2-opt，4 方案' },
  { id: 'resilience', name: '交通系统韧性评估', short: '韧性评估', desc: '结构 / 功能 / 适应三维韧性' },
]

export const EVAC_SCHEMES = [
  { key: 'all', label: '全部资源' },
  { key: 'double_amb', label: '双倍救护车' },
  { key: 'no_subway', label: '无地铁' },
  { key: 'no_heli', label: '无直升机' },
  { key: 'strict', label: '严格优先级' },
]

export const SUPPLY_SCHEMES = [
  { key: 'truck_only', label: '纯货车方案' },
  { key: 'coordinated', label: '货车+无人机协同方案' },
  { key: 'coord_double', label: '协同(加倍无人机)方案' },
  { key: 'drone_only', label: '纯无人机方案' },
]

const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now())
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const r2 = (v, d = 2) => (v === null || v === undefined || !Number.isFinite(v) ? v : Math.round(v * 10 ** d) / 10 ** d)

/** 预处理数据（解码人口栅格、构建路网），结果缓存在 data 对象上 */
export function prepareData(data) {
  if (!data._pop) data._pop = loadPopulation(data.population)
  if (data.roadNetwork && !data._graph) data._graph = new RoadGraph(data.roadNetwork)
  return data
}

export async function runSimulation(paramsIn, data, hooks = {}) {
  const params = mergeParams(DEFAULT_PARAMS, paramsIn || {})
  const { onStage, onLog } = hooks
  const T0 = now()
  const log = []
  const stageTimes = {}
  const L = (msg, level = 'info') => {
    const e = { t: r2((now() - T0) / 1000, 3), msg, level }
    log.push(e)
    onLog?.(e)
  }
  let stageStart = 0
  const begin = async (id) => {
    stageStart = now()
    onStage?.({ stage: id, status: 'running' })
    await sleep(0)
  }
  const end = async (id, summary) => {
    const ms = now() - stageStart
    stageTimes[id] = r2(ms, 1)
    if (params.stageDelayMs > ms) await sleep(params.stageDelayMs - ms)
    onStage?.({ stage: id, status: 'done', ms: r2(ms, 1), summary })
  }
  const skip = async (id, reason) => {
    stageTimes[id] = 0
    onStage?.({ stage: id, status: 'skipped', summary: reason })
    L(`跳过：${reason}`, 'warn')
  }

  prepareData(data)
  const fac = data.facilities
  const inc = params.incident
  const thresholds = GAS_THRESHOLDS[params.gas] || GAS_THRESHOLDS['氯气']
  const result = { version: ENGINE_VERSION, params, stages: STAGES, log, stageTimes }

  // ---------------- 1. 场景构建 ----------------
  await begin('scene')
  const level = beaufort(params.windSpeed)
  const dronesGrounded = params.windSpeed > params.supply.droneMaxWindMs
  L(`事故点：${inc.name || '自定义'}（${inc.lon.toFixed(5)}°E, ${inc.lat.toFixed(5)}°N）`)
  L(`危化品：${params.gas}，泄漏速率 ${params.leakRateKgMin} kg/min，有效释放高度 ${params.releaseHeightM} m`)
  L(`气象：${windDirName(params.windDir)} ${params.windSpeed} m/s（${level} 级），大气稳定度 ${params.stability} 类`)
  L(`资源池：消防站 ${fac.fire_stations.length}、仓库 ${fac.warehouses.length}、避难所 ${fac.shelters.length}、医院 ${fac.hospitals.length}、地铁站 ${fac.subway_stations?.length || 0}`)
  if (dronesGrounded) L(`风力 ${level} 级 > 6 级：无人机停飞，取消无人机直送与接力`, 'warn')
  result.scenario = {
    incident: inc, gas: params.gas, thresholds, leakRateKgMin: params.leakRateKgMin,
    wind: { speed: params.windSpeed, dir: params.windDir, level, name: windDirName(params.windDir), stability: params.stability },
    dronesGrounded, roadNetwork: !!data._graph,
  }
  await end('scene', `${inc.name || '自定义点'} · ${windDirName(params.windDir)}${level}级`)

  // ---------------- 2. 烟羽扩散 ----------------
  await begin('plume')
  const plume = computePlume(params)
  const contourLevels = [0.5, thresholds.ERPG1, thresholds.ERPG2, thresholds.ERPG3]
  const contours = plumeContours(plume, contourLevels)
  const reach = {}
  for (const [k, t] of [['erpg1', thresholds.ERPG1], ['erpg2', thresholds.ERPG2], ['erpg3', thresholds.ERPG3]]) {
    let maxD = 0
    let cnt = 0
    for (let i = 0; i < plume.n; i++) {
      for (let j = 0; j < plume.n; j++) {
        if (plume.conc[i * plume.n + j] >= t) {
          cnt++
          const d = Math.hypot(-plume.extent + j * plume.cell, -plume.extent + i * plume.cell)
          if (d > maxD) maxD = d
        }
      }
    }
    reach[k] = { maxDistM: Math.round(maxD), areaKm2: r2((cnt * plume.cell * plume.cell) / 1e6, 3) }
  }
  L(`浓度网格 ${plume.n}×${plume.n}（${plume.cell} m），最大浓度 ${plume.max.toFixed(1)} mg/m³，烟羽去向 ${Math.round(plume.plumeDirDeg)}°`)
  L(`ERPG-3(≥${thresholds.ERPG3}) 下风向 ${reach.erpg3.maxDistM} m；ERPG-2(≥${thresholds.ERPG2}) ${reach.erpg2.maxDistM} m；ERPG-1(≥${thresholds.ERPG1}) ${reach.erpg1.maxDistM} m`)
  result.plume = {
    maxConc: r2(plume.max, 3), plumeDirDeg: plume.plumeDirDeg, reach,
    contours: contours.map((c) => ({ threshold: c.threshold, geometry: c.geometry, empty: c.empty })),
    raster: plumeRaster(plume, 400),
  }
  await end('plume', `最大 ${plume.max.toFixed(1)} mg/m³ · ERPG-1 ${reach.erpg1.maxDistM} m`)

  // ---------------- 3. ERPG 分区与人口 ----------------
  await begin('zones')
  let zoneMode = params.zoneMode
  let zones = computeZones(plume, thresholds, params.zoneBuffersM, zoneMode === 'contour' ? 'contour' : 'buffered')
  let popAgg
  if (zoneMode === 'auto') {
    const zc = computeZones(plume, thresholds, params.zoneBuffersM, 'contour')
    const pc = aggregatePopulation(data._pop, zc, plume, { mode: params.population.mode })
    const tot = ZONE_KEYS.reduce((s, z) => s + pc.zones[z].total, 0)
    if (tot > 0) { zones = zc; popAgg = pc; zoneMode = 'contour' } else zoneMode = 'buffered'
    L(`分区策略 auto：原始等值线内人口 ${tot.toLocaleString()} → 采用${zoneMode === 'contour' ? '原始等值线' : '缓冲等值线'}`)
  }
  if (!popAgg) popAgg = aggregatePopulation(data._pop, zones, plume, { mode: params.population.mode })
  const { origins, shelterInPlace, shelterSectors } = buildOrigins(popAgg, data._pop, params, thresholds)
  const evacDemand = origins.reduce((s, o) => s + o.population[1] + o.population[2] + o.population[3], 0)
  const sipTotal = ZONE_KEYS.reduce((s, z) => s + shelterInPlace[z][1] + shelterInPlace[z][2] + shelterInPlace[z][3], 0)
  for (const z of ZONE_KEYS) L(`${ZONE_NAMES[z]}：人口 ${popAgg.zones[z].total.toLocaleString()}（${popAgg.zones[z].blocks} 个地块）`)
  L(`分区差异化策略：需主动疏散 ${evacDemand.toLocaleString()} 人，就地避难 ${sipTotal.toLocaleString()} 人；疏散起点 ${origins.length} 个`)
  result.zones = {
    mode: zoneMode, buffers: zones.buffers, populationMode: popAgg.mode,
    populations: popAgg.zones, circles: popAgg.circles,
    polygons: zonePolygons(plume, zones),
    evacDemand, shelterInPlace, shelterInPlaceTotal: sipTotal,
    byClassDemand: [1, 2, 3].reduce((o, k) => ({ ...o, [k]: origins.reduce((s, x) => s + x.population[k], 0) }), {}),
    populationApproximate: !!data._pop.meta?.approximate,
  }
  await end('zones', `疏散 ${evacDemand.toLocaleString()} 人 · 就地避难 ${sipTotal.toLocaleString()} 人`)

  // ---------------- 4. 路网损伤 ----------------
  await begin('roads')
  const travel = new TravelModel({ incident: inc, roads: params.roads, graph: data._graph || null })
  const closure = travel.roadClosure(TAIHE_ROAD_PROFILE_KM)
  const profileApprox = !data._graph && params.siteId !== 'taihe'
  L(`道路封闭区 ${params.roads.closureRadiusM} m，BPR 拥堵区 ${params.roads.congestionRadiusM} m（α=${params.roads.bprAlpha}, β=${params.roads.bprBeta}, v/c=${params.roads.vc}）`)
  L(`封闭道路 ${closure.closedKm.toFixed(1)} km / 影响区道路 ${closure.totalKm.toFixed(1)} km，封闭比例 ${(closure.ratio * 100).toFixed(1)}%` +
    (data._graph ? '（真实路网）' : profileApprox ? '（无路网，套用太和桥道路长度剖面，近似）' : '（论文 Step9 道路统计）'))
  if (!data._graph) L(`行程时间：几何近似模型（绕行系数 ${params.roads.circuity}，封闭区绕行，区内应急通行 ${params.roads.closureAccessKmh} km/h）`)
  result.roads = { ...closure, approx: profileApprox, closureRadiusM: params.roads.closureRadiusM,
    congestionRadiusM: params.roads.congestionRadiusM, influenceRadiusM: params.roads.influenceRadiusM,
    travelModel: data._graph ? 'road_network' : 'geometric' }
  await end('roads', `封闭比例 ${(closure.ratio * 100).toFixed(1)}%`)

  // ---------------- 5. 人员疏散 ----------------
  let evac = null
  if (params.method !== 'supply') {
    await begin('evac')
    const dests = buildDestinations(fac, inc, params.evacuation)
    const commute = fac.commute_mode_shares
    L(`疏散目的地：医院 ${dests.hospitals.length}、避难所 ${dests.shelters.length}、地铁站 ${dests.subways.length}`)
    const base = { origins, dests, travel, plume, incident: inc, params }
    const amb = params.evacuation.fleet.ambulance
    const defs = {
      all: { modes: fleetConfig(params, commute) },
      double_amb: { modes: fleetConfig(params, commute, { count: { ambulance: amb * 2 } }) },
      no_subway: { modes: fleetConfig(params, commute, { remove: ['subway'] }), noSubwayDest: true },
      no_heli: { modes: fleetConfig(params, commute, { remove: ['helicopter'] }) },
      strict: { modes: fleetConfig(params, commute), flexible: false },
    }
    const fleetDesc = Object.entries(defs.all.modes).map(([m, c]) => `${c.name}${c.count}`).join('、')
    L(`车队：${fleetDesc}（私家车数按通勤驾车比例 ${(commute.car_ratio * 100).toFixed(1)}% 调整）`)
    const schemes = {}
    for (const s of EVAC_SCHEMES) {
      const d = defs[s.key]
      const { res, summary } = runEvacScheme({ ...base, modes: d.modes, flexible: d.flexible ?? null, noSubwayDest: !!d.noSubwayDest, label: s.label })
      schemes[s.key] = {
        ...summary,
        timeline: summary.timeline.map((x) => ({ t: x.t, remaining: x.remaining, risk: r2(x.risk, 1) })),
        fleet: Object.fromEntries(Object.entries(res.fleet).map(([m, vs]) => [m, { count: vs.length, trips: vs.reduce((a, v) => a + v.trips, 0) }])),
        schedule: res.schedule.map((x) => ({
          t: x.t, pickup: r2(x.pickup), arrival: r2(x.arrival), k: x.k, mode: x.mode, count: x.count,
          origin: x.origin, dest: x.dest, destKind: x.destKind, zone: x.zone, vehicle: x.vehicle, travelMin: r2(x.travelMin),
          legs: [
            { t0: x.t, t1: r2(x.pickup), path: travel.pathLonLat({ lon: x.from[0], lat: x.from[1] }, { lon: x.via[0], lat: x.via[1] }, d.modes[x.mode].travel) },
            { t0: r2(x.pickup), t1: r2(x.arrival), path: travel.pathLonLat({ lon: x.via[0], lat: x.via[1] }, { lon: x.to[0], lat: x.to[1] }, d.modes[x.mode].travel) },
          ],
        })),
      }
      L(`方案「${s.label}」：疏散 ${summary.evacuated.toLocaleString()}/${summary.total.toLocaleString()}（${(summary.rate * 100).toFixed(1)}%），累计风险 ${Math.round(summary.totalRisk).toLocaleString()}`)
    }
    const sens = []
    for (const n of params.evacuation.sensitivityAmbulances) {
      const { summary } = runEvacScheme({ ...base, modes: fleetConfig(params, commute, { count: { ambulance: n } }), label: `救护车${n}` })
      sens.push({ n, rate: summary.rate, k1Rate: summary.byClass[1].rate, evacuated: summary.evacuated, risk: summary.totalRisk })
    }
    L(`救护车敏感性（${params.evacuation.sensitivityAmbulances.join('/')} 辆）：k=1 完成率 ${sens.map((x) => ((x.k1Rate ?? 0) * 100).toFixed(1) + '%').join(' → ')}`)
    const all = schemes.all
    L(`k=1 重伤 ${((all.byClass[1].rate ?? 0) * 100).toFixed(1)}%，k=2 脆弱群体 ${((all.byClass[2].rate ?? 0) * 100).toFixed(1)}%，k=3 一般人员 ${all.byClass[3].total ? ((all.byClass[3].rate ?? 0) * 100).toFixed(1) + '%' : '（无需疏散）'}`)
    evac = {
      schemes, sensitivityAmbulance: sens,
      origins: origins.map((o) => ({ ...o })),
      destinations: {
        hospitals: dests.hospitals.map(({ id, name, lon, lat, capacity }) => ({ id, name, lon, lat, capacity })),
        shelters: dests.shelters.map(({ id, name, lon, lat, capacity }) => ({ id, name, lon, lat, capacity })),
        subways: dests.subways.map(({ id, name, lon, lat, capacity, approx }) => ({ id, name, lon, lat, capacity, approx })),
      },
      modes: defs.all.modes,
    }
    result.evacuation = evac
    await end('evac', `疏散率 ${(all.rate * 100).toFixed(1)}% · 风险 ${(all.totalRisk / 1e4).toFixed(2)} 万`)
  } else {
    await skip('evac', '方法为“仅物资配送”')
  }

  // ---------------- 6. 物资配送 ----------------
  let supply = null
  if (params.method !== 'evac') {
    await begin('supply')
    const sp = params.supply
    const net = buildLogistics(fac, inc, sp, shelterSectors, params.method === 'dual' ? shelterInPlace : null)
    const tasks = buildTasks(net.demand)
    const nShelterNodes = net.demand.filter((d) => d.group === 'shelter').length
    L(`物流网络：供应点 ${net.supply.length}、中转站 ${net.relays.length}、需求点 ${net.demand.length}（就地避难需求点 ${nShelterNodes}）`)
    L(`配送任务 ${tasks.length} 项：` + Object.keys(SUPPLY_CATEGORIES).map((c) => `${SUPPLY_CATEGORIES[c].name}${tasks.filter((t) => t.cat === c).length}`).join('、'))
    const solver = new SupplySolver({ net, tasks, travel, sp, incident: inc, closureRadiusM: params.roads.closureRadiusM })
    const alg = params.algorithm
    const D = dronesGrounded ? 0 : sp.drones
    const cfgs = {
      truck_only: { nTrucks: sp.trucks, nDrones: 0, useDrones: false, useRelay: false },
      coordinated: { nTrucks: sp.trucks, nDrones: D, useDrones: D > 0, useRelay: D > 0 },
      coord_double: { nTrucks: sp.trucks, nDrones: D * 2, useDrones: D > 0, useRelay: D > 0 },
      drone_only: { nTrucks: 0, nDrones: D, useDrones: D > 0, useRelay: false },
    }
    const schemes = {}
    for (const s of SUPPLY_SCHEMES) {
      const sched = solver.solve({ ...cfgs[s.key], algorithm: alg })
      const sum = summarizeSupply(sched, tasks, sp.weights, s.label, solver.iterations)
      schemes[s.key] = { ...sum, config: cfgs[s.key], schedule: serializeSchedule(sched, travel) }
      L(`方案「${s.label}」：完成 ${sum.completed}/${sum.totalTasks}，Makespan ${sum.makespan.toFixed(1)} min，直送 ${sum.routes.direct}/接力 ${sum.routes.relay}` +
        (alg !== 'greedy' && sum.completed > 1 ? `，2-opt 迭代 ${sum.iterations}` : ''))
    }
    const sens = []
    for (const n of sp.sensitivityDrones) {
      const nd = dronesGrounded ? 0 : n
      const sched = solver.solve({ nTrucks: sp.trucks, nDrones: nd, useDrones: nd > 0, useRelay: nd > 0, algorithm: alg, localSearch: false })
      const sum = summarizeSupply(sched, tasks, sp.weights, `无人机${n}`)
      sens.push({ n, makespan: sum.makespan, avgTime: sum.avgTimeMin, completed: sum.completed, completionRate: sum.completionRate,
        lifeOnTime: sum.lifeOnTimeRate, penalty: sum.penalty, relay: sum.routes.relay })
    }
    L(`无人机敏感性（${sp.sensitivityDrones.join('/')} 架，仅贪心）：完成任务 ${sens.map((x) => x.completed).join(' / ')}`)
    supply = {
      schemes, sensitivityDrones: sens,
      network: {
        supply: net.supply.map(({ id, name, lon, lat, kind, stock }) => ({ id, name, lon, lat, kind, stock })),
        relays: net.relays,
        demand: net.demand.map(({ id, name, lon, lat, group, demand, population }) => ({ id, name, lon, lat, group, demand, population })),
      },
      taskCount: tasks.length,
      tasksByCategory: Object.fromEntries(Object.keys(SUPPLY_CATEGORIES).map((c) => [c, tasks.filter((t) => t.cat === c).length])),
    }
    result.supply = supply
    const co = schemes.coordinated
    await end('supply', `协同方案 ${co.completed}/${co.totalTasks} 项 · ${co.makespan.toFixed(1)} min`)
  } else {
    await skip('supply', '方法为“仅人员疏散”')
  }

  // ---------------- 7. 韧性评估 ----------------
  await begin('resilience')
  result.resilience = assessResilience(result)
  const rs = result.resilience
  L(`结构韧性：道路封闭比例 ${(rs.structural.closureRatio * 100).toFixed(1)}%，路网连通性 ${(rs.structural.connectivity * 100).toFixed(1)}%`)
  if (supply) L(`功能韧性：物资完成率 ${(rs.functional.supplyCompletion * 100).toFixed(1)}%，生命救援准时率 ${rs.functional.lifeOnTime === null ? '—' : (rs.functional.lifeOnTime * 100).toFixed(0) + '%'}`)
  if (evac) L(`功能韧性：疏散完成率 ${(rs.functional.evacRate * 100).toFixed(1)}%；适应韧性：分区策略疏散增益（k=2）${rs.adaptive.zoningGain === null ? '—' : (rs.adaptive.zoningGain * 100).toFixed(0) + '%'}`)
  await end('resilience', `路网连通性 ${(rs.structural.connectivity * 100).toFixed(0)}%`)

  result.elapsedMs = r2(now() - T0, 1)
  result.computeMs = r2(Object.values(stageTimes).reduce((a, b) => a + b, 0), 1)
  L(`计算完成：纯计算 ${(result.computeMs / 1000).toFixed(2)} s` + (params.stageDelayMs ? `（含过程展示 ${(result.elapsedMs / 1000).toFixed(2)} s）` : ''), 'success')
  return result
}

/** 三维韧性评估（论文 3.4 节 / 表 8）。supplyKey 指定用于功能韧性的配送方案 */
export function assessResilience(result, supplyKey = 'coordinated', evacKey = 'all') {
  const closureRatio = result.roads.ratio
  const sp = result.supply?.schemes
  const ev = result.evacuation?.schemes
  const s = sp?.[supplyKey]
  const e = ev?.[evacKey]
  const truck = sp?.truck_only
  const functional = {
    supplyCompletion: s ? s.completionRate : null,
    supplyMakespan: s ? s.makespan : null,
    lifeOnTime: s ? s.lifeOnTimeRate : null,
    evacRate: e ? e.rate : null,
    evacTotalRisk: e ? e.totalRisk : null,
  }
  const evacDemand = result.zones.evacDemand
  const circle3 = result.zones.circles.r3000
  const adaptive = {
    relayTasks: s ? s.routes.relay : null,
    relayIncrement: s && truck ? s.routes.relay - truck.routes.relay : null,
    droneMakespanChange: s && truck && truck.makespan > 0 ? 1 - s.makespan / truck.makespan : null,
    zoningGain: e ? e.k2ZoneRate : null,
    evacDemandReduction: circle3 ? 1 - evacDemand / circle3 : null,
  }
  const radar = [
    { key: 'supply', name: '物资配送完成率', value: functional.supplyCompletion },
    { key: 'life', name: '生命救援准时率', value: functional.lifeOnTime },
    { key: 'evac', name: '疏散完成率', value: functional.evacRate },
    { key: 'zoning', name: '分区策略疏散增益', value: adaptive.zoningGain },
    { key: 'road', name: '路网连通性', value: 1 - closureRatio, note: `1 − 道路封闭比例(${(closureRatio * 100).toFixed(1)}%)` },
  ]
  return {
    structural: { closureRatio, connectivity: 1 - closureRatio, closedKm: result.roads.closedKm, totalKm: result.roads.totalKm },
    functional, adaptive, radar, supplyKey, evacKey,
  }
}

/** 汇总单个配送方案 + 疏散方案的回放时间序列 */
export function playbackSeries(result, supplyKey, evacKey, Tmax = 180, dt = 1) {
  const out = []
  const sp = result.supply?.schemes?.[supplyKey]
  const ev = result.evacuation?.schemes?.[evacKey]
  for (let t = 0; t <= Tmax; t += dt) {
    out.push({
      t,
      delivered: sp ? sp.schedule.filter((p) => p.arrival <= t).length : 0,
      evacuated: ev ? ev.schedule.filter((x) => x.arrival <= t).reduce((s, x) => s + x.count, 0) : 0,
    })
  }
  return out
}

export const META = { POP_CLASSES, VEHICLE_MODES, MODE_KEYS, SUPPLY_CATEGORIES, ZONE_NAMES, distM }
