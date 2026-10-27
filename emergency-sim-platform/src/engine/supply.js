/**
 * 应急物资配送优化（论文 3.2 节；Step10 的逐项移植）
 *
 * 三层网络：供应点 H（消防站 + 应急仓库）→ 中转站 I（大容量场馆/公园，兼无人机起降）→ 需求点 J
 * 两种模式：直送（货车/无人机）；接力（货车送至中转站 + 无人机末端配送）
 * 目标：min Z = w1·Makespan + w2·Σ时间窗惩罚 + w3·未满足任务数
 * 求解：第一阶段 优先级贪心构造；第二阶段 同类车辆任务交换的 2-opt 局部搜索（≤200 次）
 *
 * 算法选项：
 *   two_stage        论文原版（接力与直送按最早到达竞争）
 *   two_stage_direct 直送优先改进（论文 5.3 节建议：仅当直送超时窗或需求点位于封闭区内时触发接力）
 *   greedy           仅贪心构造
 */
import { SUPPLY_CATEGORIES, SUPPLY_KEYS, SHELTER_SUPPLY_RATES } from './defaults.js'
import { distM, degDistM } from './geo.js'

/** 构建三层物流网络（Step10 build_logistics_network） */
export function buildLogistics(fac, incident, sp, shelterSectors, shelterInPlace) {
  const inRange = (f, [lo, hi]) => { const d = degDistM(f, incident); return d > lo && d < hi }
  const supply = [
    ...fac.fire_stations.filter((f) => inRange(f, sp.supplyRangeM)).slice(0, sp.maxFireStations),
    ...fac.warehouses,
  ].map((f) => ({ id: f.id, name: f.name, lon: f.lon, lat: f.lat, kind: f.type, stock: { ...f.stock } }))

  let relays = fac.shelters.filter((s) => inRange(s, sp.relayRangeM) &&
    ((s.capacity ?? 0) > sp.relayMinCapacity || s.relay_candidate)).slice(0, sp.maxRelays)
  if (relays.length < 3) {
    relays = [...relays]
    for (const s of fac.shelters) {
      if (relays.length >= 5) break
      if (!relays.includes(s) && inRange(s, [1500, 8000])) relays.push(s)
    }
  }
  relays = relays.map((s) => ({ id: s.id, name: s.name, lon: s.lon, lat: s.lat, kind: 'relay' }))

  const demand = []
  demand.push({ id: 'D_core', name: '事故核心区', lon: incident.lon, lat: incident.lat + 0.005, group: 'rescue',
    demand: { life_rescue: 100, medical: 50, protection: 200, basic: 100 } })
  const iso = [['东侧隔离点', 0.01, 0], ['西侧隔离点', -0.01, 0], ['北侧隔离点', 0, 0.01], ['南侧隔离点', 0, -0.01]]
  iso.forEach(([nm, dx, dy], i) => demand.push({ id: `D_iso${i}`, name: nm, lon: incident.lon + dx, lat: incident.lat + dy,
    group: 'rescue', demand: { life_rescue: 20, medical: 30, protection: 80, basic: 150 } }))
  for (const h of fac.hospitals) {
    if (demand.length >= sp.maxDemandNodes) break
    if (inRange(h, sp.hospitalDemandRangeM)) {
      demand.push({ id: `D_${h.id}`, name: h.name, lon: h.lon, lat: h.lat, group: 'hospital', demand: { medical: 20, basic: 30 } })
    }
  }

  // 就地避难人口 → 物资需求（Step10 load_shelter_demand_nodes；需求点取避难人口最多的扇区）
  const shelterNodes = []
  if (shelterInPlace) {
    for (const zone of ['erpg2', 'erpg1']) {
      const zp = shelterInPlace[zone]
      if (!zp) continue
      const zd = { life_rescue: 0, medical: 0, protection: 0, basic: 0 }
      for (const k of ['1', '2', '3']) {
        const rates = SHELTER_SUPPLY_RATES[`${zone}_k${k}`]
        if (!rates) continue
        for (const c of SUPPLY_KEYS) zd[c] += Math.floor((Math.floor(zp[k]) / 1000) * rates[c])
      }
      if (SUPPLY_KEYS.every((c) => zd[c] === 0)) continue
      const secs = shelterSectors.filter((s) => s.zone === zone)
        .map((s) => ({ ...s, n: s.stay[1] + s.stay[2] + s.stay[3] }))
        .sort((a, b) => b.n - a.n).slice(0, sp.shelterDemandNodes[zone] ?? 4)
      const tot = secs.reduce((s, x) => s + x.n, 0)
      for (const s of secs) {
        const share = tot ? s.n / tot : 0
        const nd = {}
        for (const c of SUPPLY_KEYS) { const q = Math.floor(zd[c] * share); if (q > 0) nd[c] = q }
        if (!Object.keys(nd).length) continue
        shelterNodes.push({ id: `D_${zone}_${s.name}`, name: `${zone.toUpperCase()}避难-${s.name}`, lon: s.lon, lat: s.lat,
          group: 'shelter', zone, population: s.n, demand: nd })
      }
    }
  }
  return { supply, relays, demand: [...demand, ...shelterNodes] }
}

export function buildTasks(demandNodes) {
  const tasks = []
  for (const d of demandNodes) {
    for (const c of SUPPLY_KEYS) {
      const q = d.demand[c] || 0
      if (q > 0) {
        const cat = SUPPLY_CATEGORIES[c]
        tasks.push({ id: tasks.length, demand: d, cat: c, qty: q, deadline: cat.windowMin, priority: cat.priority,
          penaltyRate: cat.penaltyPerMin, hard: cat.hard, weightKg: q * cat.unitKg })
      }
    }
  }
  return tasks
}

function penaltyOf(plan) {
  return plan.arrival <= plan.task.deadline ? 0 : (plan.arrival - plan.task.deadline) * plan.task.penaltyRate
}

export function supplyObjective(schedule, tasks, w) {
  if (!schedule.length) return { obj: Infinity, makespan: 0, penalty: 0, unmet: tasks.length }
  const makespan = Math.max(...schedule.map((p) => p.arrival))
  const penalty = schedule.reduce((s, p) => s + penaltyOf(p), 0)
  const served = new Set(schedule.map((p) => p.task.id))
  const unmet = tasks.filter((t) => !served.has(t.id)).length
  return { obj: w.makespan * makespan + w.penalty * penalty + w.unmet * unmet, makespan, penalty, unmet }
}

class SupplySolver {
  constructor({ net, tasks, travel, sp, incident, closureRadiusM }) {
    this.net = net
    this.tasks = tasks
    this.travel = travel
    this.sp = sp
    this.incident = incident
    this.closureRadiusM = closureRadiusM
  }

  /** 车辆行程时间：货车走道路模型，无人机直线飞行 */
  tt(v, a, b) {
    return this.travel.time(a, b, v.speed, v.type === 'drone' ? 'air' : 'ground')
  }

  makeFleet(nTrucks, nDrones) {
    const { supply, relays, demand } = this.net
    const trucks = Array.from({ length: nTrucks }, (_, i) => {
      const base = supply.length ? supply[i % supply.length] : demand[0]
      return { id: `T${i}`, type: 'truck', speed: this.sp.truckSpeedKmh, cap: this.sp.truckCapKg, base }
    })
    const drones = Array.from({ length: nDrones }, (_, i) => {
      const base = relays.length ? relays[i % relays.length] : supply.length ? supply[0] : demand[0]
      return { id: `D${i}`, type: 'drone', speed: this.sp.droneSpeedKmh, cap: this.sp.droneMaxKg, base }
    })
    return { trucks, drones }
  }

  droneLegOk(a, b) {
    return distM(a, b) <= this.sp.droneRangeM
  }

  directPlan(task, v, avail, cur, s) {
    if (v.type === 'drone' && (!this.droneLegOk(cur, s) || !this.droneLegOk(s, task.demand))) return null
    const t1 = this.tt(v, cur, s)
    const t2 = this.tt(v, s, task.demand)
    const dep = Math.max(avail, 0)
    return { task, vehicle: v, supply: s, relay: null, departure: dep, atSupply: dep + t1, atRelay: null,
      arrival: dep + t1 + t2, route: 'direct', from: cur }
  }

  relayPlan(task, v, avail, cur, s, r) {
    const dd = distM(r, task.demand)
    if (dd > this.sp.droneRangeM) return null
    const dep = Math.max(avail, 0)
    const t1 = dep + this.tt(v, cur, s)
    const t2 = t1 + this.tt(v, s, r)
    const droneT = (dd / 1000 / this.sp.droneSpeedKmh) * 60
    return { task, vehicle: v, supply: s, relay: r, departure: dep, atSupply: t1, atRelay: t2,
      droneStart: t2 + this.sp.droneLoadMin, arrival: t2 + this.sp.droneLoadMin + droneT, route: 'relay', from: cur }
  }

  greedy({ trucks, drones, useDrones, useRelay, directFirst }) {
    const order = [...this.tasks].sort((a, b) => (a.priority - b.priority) || (a.deadline - b.deadline) || (a.id - b.id))
    const stock = new Map(this.net.supply.map((s) => [s.id, { ...s.stock }]))
    const vehicles = useDrones ? [...trucks, ...drones] : [...trucks]
    const avail = new Map(vehicles.map((v) => [v.id, 0]))
    const pos = new Map(vehicles.map((v) => [v.id, v.base]))
    const schedule = []
    for (const task of order) {
      let best = null
      for (const v of vehicles) {
        if (v.type === 'drone' && task.weightKg > v.cap) continue
        const a = avail.get(v.id)
        const cur = pos.get(v.id)
        for (const s of this.net.supply) {
          if ((stock.get(s.id)[task.cat] || 0) <= 0) continue
          const p = this.directPlan(task, v, a, cur, s)
          if (p && (!best || p.arrival < best.arrival)) best = p
        }
      }
      // 接力（仅货车）
      const allowRelay = useRelay && (!directFirst || !best || best.arrival > task.deadline ||
        distM(task.demand, this.incident) <= this.closureRadiusM)
      if (allowRelay) {
        for (const v of trucks) {
          const a = avail.get(v.id)
          const cur = pos.get(v.id)
          for (const r of this.net.relays) {
            for (const s of this.net.supply) {
              if ((stock.get(s.id)[task.cat] || 0) <= 0) continue
              const p = this.relayPlan(task, v, a, cur, s, r)
              if (p && (!best || p.arrival < best.arrival)) best = p
            }
          }
        }
      }
      if (best) {
        avail.set(best.vehicle.id, best.arrival + this.sp.unloadMin)
        pos.set(best.vehicle.id, best.route === 'direct' ? task.demand : best.relay)
        const st = stock.get(best.supply.id)
        st[task.cat] = Math.max(0, (st[task.cat] || 0) - task.qty)
        schedule.push(best)
      }
    }
    return schedule
  }

  /** 将任务改派给另一车辆（自其基地出发，保持原路线类型；论文 _reassign 的修正版） */
  reassign(plan, v) {
    if (plan.route === 'relay') return this.relayPlan(plan.task, v, 0, v.base, plan.supply, plan.relay)
    return this.directPlan(plan.task, v, 0, v.base, plan.supply)
  }

  localSearch(schedule, maxIter) {
    if (schedule.length < 2) return schedule
    let bestObj = supplyObjective(schedule, this.tasks, this.sp.weights).obj
    let improved = true
    let iter = 0
    while (improved && iter < maxIter) {
      improved = false
      iter++
      outer: for (let i = 0; i < schedule.length; i++) {
        for (let j = i + 1; j < schedule.length; j++) {
          if (schedule[i].vehicle.type !== schedule[j].vehicle.type) continue
          const ni = this.reassign(schedule[i], schedule[j].vehicle)
          const nj = this.reassign(schedule[j], schedule[i].vehicle)
          if (!ni || !nj) continue
          const cand = schedule.slice()
          cand[i] = ni
          cand[j] = nj
          const o = supplyObjective(cand, this.tasks, this.sp.weights).obj
          if (o < bestObj - 0.01) {
            schedule = cand
            bestObj = o
            improved = true
            break outer
          }
        }
      }
    }
    this.iterations = iter
    return schedule
  }

  solve({ nTrucks, nDrones, useDrones, useRelay, algorithm, localSearch = true }) {
    const { trucks, drones } = this.makeFleet(nTrucks, nDrones)
    let schedule = this.greedy({ trucks, drones, useDrones, useRelay, directFirst: algorithm === 'two_stage_direct' })
    this.iterations = 0
    if (localSearch && algorithm !== 'greedy' && schedule.length > 1) schedule = this.localSearch(schedule, this.sp.maxIter)
    return schedule
  }
}

export function summarizeSupply(schedule, tasks, w, label, iterations = 0) {
  const o = supplyObjective(schedule, tasks, w)
  const times = schedule.map((p) => p.arrival)
  const byCategory = {}
  for (const c of SUPPLY_KEYS) {
    const cp = schedule.filter((p) => p.task.cat === c)
    const total = tasks.filter((t) => t.cat === c).length
    const dl = SUPPLY_CATEGORIES[c].windowMin
    const onTime = cp.filter((p) => p.arrival <= dl).length
    byCategory[c] = {
      total, completed: cp.length, onTime,
      onTimeRate: cp.length ? onTime / cp.length : null,
      avgTimeMin: cp.length ? cp.reduce((s, p) => s + p.arrival, 0) / cp.length : 0,
      maxTimeMin: cp.length ? Math.max(...cp.map((p) => p.arrival)) : 0,
      deadlineMin: dl,
    }
  }
  return {
    label,
    totalTasks: tasks.length,
    completed: schedule.length,
    unmet: o.unmet,
    completionRate: tasks.length ? schedule.length / tasks.length : 0,
    objective: Number.isFinite(o.obj) ? o.obj : null,
    makespan: o.makespan,
    avgTimeMin: times.length ? times.reduce((a, b) => a + b, 0) / times.length : 0,
    penalty: o.penalty,
    routes: {
      direct: schedule.filter((p) => p.route === 'direct').length,
      relay: schedule.filter((p) => p.route === 'relay').length,
      truck: schedule.filter((p) => p.vehicle.type === 'truck').length,
      drone: schedule.filter((p) => p.vehicle.type === 'drone').length,
    },
    byCategory,
    lifeOnTimeRate: byCategory.life_rescue.onTimeRate,
    iterations,
  }
}

/** 调度方案 → 可序列化记录（含地图回放所需的分段时刻） */
export function serializeSchedule(schedule, travel) {
  return schedule.map((p) => {
    const legs = []
    const truckLike = p.vehicle.type === 'truck'
    const kind = truckLike ? 'ground' : 'air'
    legs.push({ type: p.vehicle.type, t0: p.departure, t1: p.atSupply, path: travel.pathLonLat(p.from, p.supply, kind) })
    if (p.route === 'direct') {
      legs.push({ type: p.vehicle.type, t0: p.atSupply, t1: p.arrival, path: travel.pathLonLat(p.supply, p.task.demand, kind) })
    } else {
      legs.push({ type: 'truck', t0: p.atSupply, t1: p.atRelay, path: travel.pathLonLat(p.supply, p.relay, 'ground') })
      legs.push({ type: 'drone', t0: p.droneStart, t1: p.arrival, path: [[p.relay.lon, p.relay.lat], [p.task.demand.lon, p.task.demand.lat]] })
    }
    return {
      taskId: p.task.id, cat: p.task.cat, qty: p.task.qty, demand: p.task.demand.name, demandId: p.task.demand.id,
      vehicle: p.vehicle.id, vehicleType: p.vehicle.type, supply: p.supply.name, relay: p.relay ? p.relay.name : null,
      route: p.route, departure: p.departure, arrival: p.arrival, deadline: p.task.deadline,
      penalty: penaltyOf(p), legs,
    }
  })
}

export { SupplySolver }
