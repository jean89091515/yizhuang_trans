/**
 * 多类型人员疏散优化（论文 3.3 节；Step11 evacuation_dispatch 的逐行移植）
 *
 * 风险感知时间步进调度：Δt=5 min，T=180 min。每步按 k=1→2→3 优先级、
 * 各优先级内按 ω_k·ρ(i)·H_k(i) 降序处理起点，为每辆可用车辆分配“车→起点→目的地”
 * 总时间最短的目的地；车辆返回时间 = 到达 + 行程 + 2 min 卸客。
 * 弹性优先级：公交/地铁车队末尾 25% 仅服务 k=3。
 * 目标函数 Z = w1·Z1(加权疏散时间) + w2·Z2(动态风险暴露) + w3·Z3(未服务惩罚)。
 */
import { POP_CLASSES, VEHICLE_MODES, MODE_KEYS, EVAC_RULES, ZONE_KEYS } from './defaults.js'
import { degDistM, distM } from './geo.js'

/** 由分区扇区人口生成疏散起点与就地避难人口（Step11 build_evacuation_network_erpg） */
export function buildOrigins(popAgg, popData, params, thresholds) {
  const k1r = params.population.k1Ratio
  const nominal = { erpg3: thresholds?.ERPG3 ?? 20, erpg2: thresholds?.ERPG2 ?? 3, erpg1: thresholds?.ERPG1 ?? 1 }
  const inc = params.incident
  const u = Math.max(params.windSpeed, 0.5)
  const age = popData.age || { children: 0.12, elderly: 0.15 }
  const k2r = age.children + age.elderly
  const k3r = Math.max(0, 1 - k1r - k2r)
  const origins = []
  const shelterInPlace = {}
  const shelterSectors = []
  let id = 0
  for (const z of ZONE_KEYS) {
    const rules = EVAC_RULES[z]
    const sip = { 1: 0, 2: 0, 3: 0 }
    const secs = popAgg.sectors.filter((s) => s.zone === z).sort((a, b) => a.sector - b.sector)
    for (const s of secs) {
      const k = { 1: Math.floor(s.pop * k1r), 2: Math.floor(s.pop * k2r), 3: Math.floor(s.pop * k3r) }
      const evac = { 1: rules[1] ? k[1] : 0, 2: rules[2] ? k[2] : 0, 3: rules[3] ? k[3] : 0 }
      const stay = { 1: rules[1] ? 0 : k[1], 2: rules[2] ? 0 : k[2], 3: rules[3] ? 0 : k[3] }
      sip[1] += stay[1]; sip[2] += stay[2]; sip[3] += stay[3]
      const label = `${z.toUpperCase()}-${s.sectorName}`
      if (evac[1] + evac[2] + evac[3] > 0) {
        const rhoLocal = s.rho ?? 0
        const rho = params.risk?.nominalByZone ? Math.max(rhoLocal, nominal[z]) : rhoLocal
        const rM = distM(inc, s)
        const exposureEndMin = params.risk?.dynamic ? params.leakDurationMin + rM / u / 60 : Infinity
        origins.push({ id: id++, name: label, lon: s.lon, lat: s.lat, zone: z, population: evac, sectorPop: Math.round(s.pop),
          rho, rhoLocal, exposureEndMin, distM: Math.round(rM) })
      }
      if (stay[1] + stay[2] + stay[3] > 0) {
        shelterSectors.push({ zone: z, name: s.sectorName, lon: s.lon, lat: s.lat, stay })
      }
    }
    shelterInPlace[z] = sip
  }
  return { origins, shelterInPlace, shelterSectors }
}

/** 疏散目的地（Step11：医院 2–12 km 前 12 个；避难所按容量降序 2–12 km 前 15 个；地铁站 1.5–8 km 前 8 个） */
export function buildDestinations(fac, incident, ev) {
  const inRange = (f, [lo, hi]) => { const d = degDistM(f, incident); return d > lo && d < hi }
  const hospitals = fac.hospitals.filter((h) => inRange(h, ev.hospitalRangeM)).slice(0, ev.maxHospitals)
    .map((h) => ({ ...h, kind: 'hospital', capacity: h.beds ?? 200 }))
  const shelters = [...fac.shelters].sort((a, b) => (b.capacity ?? 2000) - (a.capacity ?? 2000))
    .filter((s) => inRange(s, ev.shelterRangeM)).slice(0, ev.maxShelters)
    .map((s) => ({ ...s, kind: 'shelter', capacity: s.capacity ?? 2000 }))
  const subways = (fac.subway_stations || []).filter((s) => inRange(s, ev.subwayRangeM)).slice(0, ev.maxSubways)
    .map((s) => ({ ...s, kind: 'subway', capacity: s.capacity ?? 8000 }))
  return { hospitals, shelters, subways }
}

export function carCount(commute) {
  const r = commute?.car_ratio ?? 0.30
  return Math.max(20, Math.floor((100 * r) / 0.30))
}

/** 车队配置（count 覆盖、方案增删） */
export function fleetConfig(params, commute, override = {}) {
  const f = params.evacuation.fleet
  const modes = {}
  for (const m of MODE_KEYS) {
    if (override.remove?.includes(m)) continue
    const count = m === 'car' ? (f.car ?? carCount(commute)) : f[m]
    modes[m] = { ...VEHICLE_MODES[m], count: override.count?.[m] ?? count }
  }
  return modes
}

/**
 * 时间步进调度主循环。
 * origins: [{id,name,lon,lat,zone,population:{1,2,3}}]
 * destMap: {1:[...],2:[...],3:[...]}（节点含 capacity，会被修改，调用方需传入副本）
 */
export function evacuationDispatch({ origins, destMap, modes, travel, plume, incident, opts }) {
  const { Tmax, dt, flexiblePriority, k3ReservedRatio, unloadMin } = opts
  const schedule = []
  const timeline = []
  const steps = []
  for (let t = 0; t < Tmax; t += dt) steps.push(t)

  const fleet = {}
  for (const [m, cfg] of Object.entries(modes)) {
    fleet[m] = []
    for (let i = 0; i < cfg.count; i++) {
      const ang = (2 * Math.PI * i) / Math.max(1, cfg.count)
      fleet[m].push({
        id: `${m}_${i}`, availableAt: 0,
        lon: incident.lon + 0.015 * Math.cos(ang), lat: incident.lat + 0.015 * Math.sin(ang),
        trips: 0, moved: 0, reservedK3: false,
      })
    }
  }
  if (flexiblePriority) {
    for (const m of ['bus', 'subway']) {
      if (!fleet[m] || fleet[m].length === 0) continue
      const nr = Math.max(1, Math.floor(fleet[m].length * k3ReservedRatio))
      for (let i = 0; i < nr; i++) fleet[m][fleet[m].length - 1 - i].reservedK3 = true
    }
  }

  const remaining = new Map(origins.map((o) => [o.id, { ...o.population }]))
  const rho0 = new Map(origins.map((o) => [o.id, o.rho ?? plume.concAt(o.lon, o.lat)]))
  const end = new Map(origins.map((o) => [o.id, o.exposureEndMin ?? Infinity]))
  let curT = 0
  const rho = { get: (id) => (curT <= end.get(id) ? rho0.get(id) : 0) }
  const totalRemaining = () => { let s = 0; for (const r of remaining.values()) s += r[1] + r[2] + r[3]; return s }

  for (const t of steps) {
    curT = t
    const tot = totalRemaining()
    if (tot === 0) break
    let risk = 0
    for (const o of origins) {
      const r = remaining.get(o.id)
      for (const k of [1, 2, 3]) risk += POP_CLASSES[k].weight * rho.get(o.id) * r[k]
    }
    timeline.push({ t, remaining: tot, risk })

    for (const k of [1, 2, 3]) {
      const allowed = POP_CLASSES[k].modes
      const scored = []
      for (const o of origins) {
        const ppl = remaining.get(o.id)[k]
        if (ppl <= 0) continue
        scored.push([POP_CLASSES[k].weight * rho.get(o.id) * ppl, -o.id, o])
      }
      scored.sort((a, b) => (b[0] - a[0]) || (b[1] - a[1]))
      for (const [, , o] of scored) {
        let ppl = remaining.get(o.id)[k]
        if (ppl <= 0) continue
        const dests = destMap[k] || []
        if (!dests.length) continue
        const destsAvail = dests.filter((d) => d.capacity > 0)
        if (!destsAvail.length) continue
        for (const m of allowed) {
          if (!fleet[m]) continue
          const cfg = modes[m]
          for (const veh of fleet[m]) {
            if (veh.availableAt > t) continue
            if (flexiblePriority && veh.reservedK3 && k !== 3) continue
            if (ppl <= 0) break
            const tToOrigin = travel.time(veh, o, cfg.speedKmh, cfg.travel)
            let best = null
            let bestTotal = Infinity
            for (const d of destsAvail) {
              if (d.capacity <= 0) continue
              const tot2 = tToOrigin + travel.time(o, d, cfg.speedKmh, cfg.travel)
              if (tot2 < bestTotal) { bestTotal = tot2; best = d }
            }
            if (!best) continue
            const tOD = travel.time(o, best, cfg.speedKmh, cfg.travel)
            const arrival = t + tToOrigin + tOD
            const ret = arrival + tOD + unloadMin
            const batch = Math.min(ppl, cfg.capacity, Math.floor(best.capacity))
            if (batch <= 0) continue
            schedule.push({
              t, depart: t, pickup: t + tToOrigin, arrival, origin: o.name, originId: o.id, dest: best.name,
              destKind: best.kind, k, mode: m, count: batch, travelMin: tOD, vehicle: veh.id, zone: o.zone,
              from: [veh.lon, veh.lat], via: [o.lon, o.lat], to: [best.lon, best.lat],
            })
            const r = remaining.get(o.id)
            r[k] = Math.max(0, r[k] - batch)
            ppl = r[k]
            best.capacity -= batch
            veh.availableAt = ret
            veh.lon = best.lon
            veh.lat = best.lat
            veh.trips++
            veh.moved += batch
          }
        }
      }
    }
  }
  timeline.push({ t: steps.length ? steps[steps.length - 1] : Tmax, remaining: totalRemaining(), risk: 0, final: true })
  return { schedule, timeline, remaining, fleet }
}

export function evacObjectives(res, origins, weights, pUnsat) {
  const z1 = res.schedule.reduce((s, x) => s + POP_CLASSES[x.k].weight * x.travelMin * x.count, 0)
  const z2 = res.timeline.reduce((s, x) => s + x.risk, 0)
  let z3 = 0
  for (const o of origins) {
    const r = res.remaining.get(o.id)
    for (const k of [1, 2, 3]) z3 += pUnsat * POP_CLASSES[k].weight * r[k]
  }
  return { obj: weights.z1 * z1 + weights.z2 * z2 + weights.z3 * z3, z1, z2, z3 }
}

export function summarizeEvac(res, origins, label, params) {
  const evacuated = res.schedule.reduce((s, x) => s + x.count, 0)
  let remaining = 0
  for (const r of res.remaining.values()) remaining += r[1] + r[2] + r[3]
  const byClass = {}
  for (const k of [1, 2, 3]) {
    const ks = res.schedule.filter((x) => x.k === k)
    const ev = ks.reduce((s, x) => s + x.count, 0)
    let rem = 0
    for (const o of origins) rem += res.remaining.get(o.id)[k]
    byClass[k] = {
      evacuated: ev, total: ev + rem, rate: ev + rem ? ev / (ev + rem) : null,
      avgTravelMin: ks.length ? ks.reduce((s, x) => s + x.travelMin, 0) / ks.length : 0,
    }
  }
  const byMode = {}
  for (const m of MODE_KEYS) {
    const ms = res.schedule.filter((x) => x.mode === m)
    byMode[m] = { trips: ms.length, people: ms.reduce((s, x) => s + x.count, 0) }
  }
  const byZone = {}
  for (const z of ZONE_KEYS) {
    const zs = res.schedule.filter((x) => x.zone === z)
    const ev = zs.reduce((s, x) => s + x.count, 0)
    let tot = 0
    for (const o of origins.filter((o) => o.zone === z)) tot += o.population[1] + o.population[2] + o.population[3]
    byZone[z] = { evacuated: ev, total: tot, rate: tot ? ev / tot : null }
  }
  const obj = evacObjectives(res, origins, params.evacuation.weights, params.evacuation.pUnsat)
  const totalRisk = obj.z2
  // ERPG 分区中需疏散的 k=2 脆弱群体完成率（分区策略疏散增益）
  const k2Zones = ZONE_KEYS.filter((z) => EVAC_RULES[z][2])
  const k2Sched = res.schedule.filter((x) => x.k === 2 && k2Zones.includes(x.zone)).reduce((s, x) => s + x.count, 0)
  const k2Total = origins.filter((o) => k2Zones.includes(o.zone)).reduce((s, o) => s + o.population[2], 0)
  return {
    label, evacuated, remaining, total: evacuated + remaining,
    rate: evacuated + remaining ? evacuated / (evacuated + remaining) : 0,
    byClass, byMode, byZone, totalRisk, objective: obj,
    k2ZoneRate: k2Total ? k2Sched / k2Total : null,
    makespan: res.schedule.length ? Math.max(...res.schedule.map((x) => x.arrival)) : 0,
    timeline: res.timeline,
  }
}

/** 运行一个疏散方案（自动深拷贝目的地容量） */
export function runEvacScheme({ origins, dests, modes, travel, plume, incident, params, flexible = null, noSubwayDest = false, label }) {
  const clone = (arr) => arr.map((d) => ({ ...d }))
  const H = clone(dests.hospitals)
  const S = clone(dests.shelters)
  const M = clone(dests.subways)
  // 与 Step11 一致：k=1 与 k=2 共享同一批医院对象（容量共用）
  const destMap = { 1: H, 2: [...H, ...S], 3: noSubwayDest ? [...S] : [...S, ...M] }
  const opts = {
    ...params.evacuation,
    flexiblePriority: flexible === null ? params.evacuation.flexiblePriority : flexible,
  }
  const res = evacuationDispatch({ origins, destMap, modes, travel, plume, incident, opts })
  const summary = summarizeEvac(res, origins, label, params)
  return { res, summary }
}
