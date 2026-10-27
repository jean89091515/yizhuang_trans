/**
 * 行程时间模型（论文 3.1.3 节：道路封闭 + BPR 拥堵）
 *
 * 1) 有路网（public/data/road_network.json，由导出脚本从 road_network_graph.gpickle 生成）：
 *    与 network_router.py 相同——封闭半径内路段删除；拥堵半径内路段
 *    t = t0·(1+α(v/c)^β)·(1+proximity)，proximity=(Rc−r)/Rc；Dijkstra 最短时间。
 *    车辆限速取 min(道路限速, 车辆速度)。不可达时退回 2)。
 * 2) 无路网（默认）：几何近似模型——
 *    直线距离×绕行系数；穿越封闭圆时绕行（切线+圆弧最短路径）；端点在封闭区内时，
 *    区内段按应急通行速度行驶；沿路径逐段按与上式相同的 BPR 拥堵系数折算时间。
 * 空中（直升机/无人机）按直线距离/速度；地铁按 1.2×直线距离/速度。
 */
import { makeLocal } from './geo.js'

export class TravelModel {
  constructor({ incident, roads, graph = null }) {
    this.local = makeLocal(incident.lon, incident.lat)
    this.roads = roads
    this.graph = graph
    this.cache = new Map()
    const { bprAlpha, bprBeta, vc } = roads
    this.bpr = 1 + bprAlpha * Math.pow(vc, bprBeta)
    if (graph) {
      graph.applyIncident(this.local, roads, this.bpr)
      graph.speedCap = roads.vehicleSpeedCap !== false
    }
  }

  congestionFactor(r) {
    const Rc = this.roads.congestionRadiusM
    if (r >= Rc) return 1
    return this.bpr * (1 + (Rc - r) / Rc)
  }

  /** 两点间行程时间（分钟）。kind: ground | air | rail */
  time(a, b, speedKmh, kind = 'ground') {
    const key = `${kind}|${speedKmh}|${a.lon.toFixed(5)},${a.lat.toFixed(5)}|${b.lon.toFixed(5)},${b.lat.toFixed(5)}`
    let t = this.cache.get(key)
    if (t !== undefined) return t
    const [ax, ay] = this.local.toXY(a.lon, a.lat)
    const [bx, by] = this.local.toXY(b.lon, b.lat)
    const d = Math.hypot(bx - ax, by - ay)
    if (kind === 'air') t = (d / 1000 / speedKmh) * 60
    else if (kind === 'rail') t = ((1.2 * d) / 1000 / speedKmh) * 60
    else {
      t = this.graph ? this.graph.timeMin(a, b, speedKmh) : null
      if (t === null || !Number.isFinite(t)) t = this.geometricTime(ax, ay, bx, by, speedKmh)
    }
    this.cache.set(key, t)
    return t
  }

  /** 几何近似路径的折线（局部米制坐标），同时用于地图展示 */
  geometricPath(ax, ay, bx, by) {
    const R = this.roads.closureRadiusM
    const ra = Math.hypot(ax, ay)
    const rb = Math.hypot(bx, by)
    const dx = bx - ax
    const dy = by - ay
    const L2 = dx * dx + dy * dy
    if (ra <= R || rb <= R || L2 === 0) return [[ax, ay], [bx, by]]
    // 线段到圆心最近点
    const tt = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / L2))
    const px = ax + tt * dx
    const py = ay + tt * dy
    if (Math.hypot(px, py) >= R) return [[ax, ay], [bx, by]]
    // 绕行：切点-圆弧-切点（取较短一侧）
    const thA = Math.atan2(ay, ax)
    const thB = Math.atan2(by, bx)
    const alphaA = Math.acos(R / ra)
    const alphaB = Math.acos(R / rb)
    let best = null
    for (const sgn of [1, -1]) {
      const ta = thA + sgn * alphaA
      const tb = thB - sgn * alphaB
      let sweep = sgn * (tb - ta)
      sweep = ((sweep % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)
      const len = Math.sqrt(ra * ra - R * R) + Math.sqrt(rb * rb - R * R) + R * sweep
      if (!best || len < best.len) best = { len, ta, sweep, sgn }
    }
    const pts = [[ax, ay]]
    const steps = Math.max(2, Math.ceil(best.sweep / 0.2))
    const Rp = R * 1.02
    for (let k = 0; k <= steps; k++) {
      const th = best.ta + best.sgn * (best.sweep * k) / steps
      pts.push([Rp * Math.cos(th), Rp * Math.sin(th)])
    }
    pts.push([bx, by])
    return pts
  }

  geometricTime(ax, ay, bx, by, speedKmh) {
    const { circuity, closureRadiusM: R, closureAccessKmh } = this.roads
    const pts = this.geometricPath(ax, ay, bx, by)
    let minutes = 0
    for (let k = 0; k < pts.length - 1; k++) {
      const [x0, y0] = pts[k]
      const [x1, y1] = pts[k + 1]
      const segLen = Math.hypot(x1 - x0, y1 - y0)
      if (segLen === 0) continue
      const ns = Math.max(1, Math.ceil(segLen / 200))
      const sub = segLen / ns
      for (let s = 0; s < ns; s++) {
        const f = (s + 0.5) / ns
        const r = Math.hypot(x0 + f * (x1 - x0), y0 + f * (y1 - y0))
        if (r < R) minutes += ((sub * circuity) / 1000 / Math.min(speedKmh, closureAccessKmh)) * 60
        else minutes += ((sub * circuity) / 1000 / speedKmh) * 60 * this.congestionFactor(r)
      }
    }
    return minutes
  }

  /** 供地图绘制的路径（经纬度数组） */
  pathLonLat(a, b, kind = 'ground') {
    if (kind !== 'ground') return [[a.lon, a.lat], [b.lon, b.lat]]
    if (this.graph) {
      const p = this.graph.pathLonLat(a, b)
      if (p) return p
    }
    const [ax, ay] = this.local.toXY(a.lon, a.lat)
    const [bx, by] = this.local.toXY(b.lon, b.lat)
    return this.geometricPath(ax, ay, bx, by).map(([x, y]) => this.local.toLL(x, y))
  }

  /** 道路封闭比例（结构韧性）：封闭半径内道路长度 / 影响半径内道路长度 */
  roadClosure(profileKm) {
    const { closureRadiusM: Rc, influenceRadiusM: Ri } = this.roads
    if (this.graph) {
      const s = this.graph.lengthWithin(this.local, [Rc, Ri])
      return { closedKm: s[0], totalKm: s[1], ratio: s[1] ? s[0] / s[1] : 0, source: 'road_network' }
    }
    const L = (r) => interpProfile(profileKm, r)
    const closedKm = L(Rc)
    const totalKm = L(Ri)
    return { closedKm, totalKm, ratio: totalKm ? closedKm / totalKm : 0, source: 'profile' }
  }
}

/** 道路长度-半径剖面线性插值（profile: [[r_m, km], ...]，含 [0,0]） */
function interpProfile(profile, r) {
  const p = [[0, 0], ...profile].sort((a, b) => a[0] - b[0])
  if (r <= 0) return 0
  for (let i = 1; i < p.length; i++) {
    if (r <= p[i][0]) {
      const [r0, k0] = p[i - 1]
      const [r1, k1] = p[i]
      // 道路长度近似随面积增长 → 按 r² 插值
      const f = (r * r - r0 * r0) / (r1 * r1 - r0 * r0)
      return k0 + f * (k1 - k0)
    }
  }
  const [rl, kl] = p[p.length - 1]
  return kl * (r * r) / (rl * rl)
}

/** 太和桥周边道路长度剖面（论文 Step9 road_impacts：500m/1km/3km/5km） */
export const TAIHE_ROAD_PROFILE_KM = [
  [500, 60.03],
  [1000, 96.73],
  [3000, 228.85],
  [5000, 505.28],
]

// ---------------------------------------------------------------------
// 可选：真实路网（导出脚本生成 road_network.json）
// ---------------------------------------------------------------------

class MinHeap {
  constructor() { this.k = []; this.v = [] }
  get size() { return this.k.length }
  push(key, val) {
    const k = this.k, v = this.v
    let i = k.length
    k.push(key); v.push(val)
    while (i > 0) {
      const p = (i - 1) >> 1
      if (k[p] <= key) break
      k[i] = k[p]; v[i] = v[p]; i = p
    }
    k[i] = key; v[i] = val
  }
  pop() {
    const k = this.k, v = this.v
    const topV = v[0]
    const lastK = k.pop(), lastV = v.pop()
    const n = k.length
    if (n > 0) {
      let i = 0
      while (true) {
        let c = 2 * i + 1
        if (c >= n) break
        if (c + 1 < n && k[c + 1] < k[c]) c++
        if (k[c] >= lastK) break
        k[i] = k[c]; v[i] = v[c]; i = c
      }
      k[i] = lastK; v[i] = lastV
    }
    return topV
  }
}

export class RoadGraph {
  /** json: { nodes:[lon,lat,...], edges:[u,v,length_m,speed_kmh,...] } */
  constructor(json) {
    const nodes = json.nodes
    const N = nodes.length / 2
    this.N = N
    this.lon = new Float64Array(N)
    this.lat = new Float64Array(N)
    for (let i = 0; i < N; i++) { this.lon[i] = nodes[2 * i]; this.lat[i] = nodes[2 * i + 1] }
    const E = json.edges.length / 4
    const deg = new Int32Array(N + 1)
    for (let e = 0; e < E; e++) deg[json.edges[4 * e] + 1]++
    for (let i = 0; i < N; i++) deg[i + 1] += deg[i]
    this.off = deg
    this.to = new Int32Array(E)
    this.len = new Float64Array(E)
    this.spd = new Float64Array(E)
    const fill = deg.slice(0, N)
    for (let e = 0; e < E; e++) {
      const u = json.edges[4 * e]
      const p = fill[u]++
      this.to[p] = json.edges[4 * e + 1]
      this.len[p] = json.edges[4 * e + 2]
      this.spd[p] = Math.max(5, json.edges[4 * e + 3])
    }
    this.factor = new Float64Array(E).fill(1) // Infinity=封闭
    this.ssspCache = new Map()
    // 最近节点：0.01° 网格桶
    this.bucket = new Map()
    for (let i = 0; i < N; i++) {
      const key = `${Math.floor(this.lon[i] * 100)},${Math.floor(this.lat[i] * 100)}`
      if (!this.bucket.has(key)) this.bucket.set(key, [])
      this.bucket.get(key).push(i)
    }
    this.nearestCache = new Map()
  }

  applyIncident(local, roads, bpr) {
    const { closureRadiusM: R, congestionRadiusM: Rc } = roads
    for (let u = 0; u < this.N; u++) {
      for (let p = this.off[u]; p < this.off[u + 1]; p++) {
        const v = this.to[p]
        const [x, y] = local.toXY((this.lon[u] + this.lon[v]) / 2, (this.lat[u] + this.lat[v]) / 2)
        const r = Math.hypot(x, y)
        this.factor[p] = r < R ? Infinity : r < Rc ? bpr * (1 + (Rc - r) / Rc) : 1
      }
    }
    this.ssspCache.clear()
  }

  nearest(lon, lat) {
    const key = `${lon.toFixed(6)},${lat.toFixed(6)}`
    if (this.nearestCache.has(key)) return this.nearestCache.get(key)
    const cx = Math.floor(lon * 100)
    const cy = Math.floor(lat * 100)
    let best = -1
    let bd = Infinity
    for (let ring = 0; ring < 6 && (best < 0 || ring < 2); ring++) {
      for (let dx = -ring; dx <= ring; dx++) {
        for (let dy = -ring; dy <= ring; dy++) {
          if (Math.max(Math.abs(dx), Math.abs(dy)) !== ring) continue
          const arr = this.bucket.get(`${cx + dx},${cy + dy}`)
          if (!arr) continue
          for (const i of arr) {
            const d = (this.lon[i] - lon) ** 2 + (this.lat[i] - lat) ** 2
            if (d < bd) { bd = d; best = i }
          }
        }
      }
    }
    this.nearestCache.set(key, best)
    return best
  }

  sssp(src, speedKmh) {
    const key = `${src}|${speedKmh}`
    let r = this.ssspCache.get(key)
    if (r) return r
    const dist = new Float64Array(this.N).fill(Infinity)
    const prev = new Int32Array(this.N).fill(-1)
    const vms = this.speedCap === false ? Infinity : speedKmh / 3.6
    dist[src] = 0
    const h = new MinHeap()
    h.push(0, src)
    while (h.size) {
      const dkey = h.k[0]
      const u = h.pop()
      if (dkey > dist[u]) continue
      for (let p = this.off[u]; p < this.off[u + 1]; p++) {
        const f = this.factor[p]
        if (f === Infinity) continue
        const w = (this.len[p] / Math.min(this.spd[p] / 3.6, vms)) * f
        const nd = dkey + w
        const v = this.to[p]
        if (nd < dist[v]) { dist[v] = nd; prev[v] = u; h.push(nd, v) }
      }
    }
    r = { dist, prev }
    if (this.ssspCache.size > 400) this.ssspCache.clear()
    this.ssspCache.set(key, r)
    return r
  }

  timeMin(a, b, speedKmh) {
    const s = this.nearest(a.lon, a.lat)
    const t = this.nearest(b.lon, b.lat)
    if (s < 0 || t < 0) return null
    if (s === t) return 0
    const d = this.sssp(s, speedKmh).dist[t]
    return Number.isFinite(d) ? d / 60 : null
  }

  pathLonLat(a, b, speedKmh = 40) {
    const s = this.nearest(a.lon, a.lat)
    const t = this.nearest(b.lon, b.lat)
    if (s < 0 || t < 0) return null
    const { dist, prev } = this.sssp(s, speedKmh)
    if (!Number.isFinite(dist[t])) return null
    const out = []
    for (let v = t; v !== -1; v = prev[v]) out.push([this.lon[v], this.lat[v]])
    out.push([a.lon, a.lat])
    out.reverse()
    out.push([b.lon, b.lat])
    return out
  }

  lengthWithin(local, radii) {
    const sums = radii.map(() => 0)
    for (let u = 0; u < this.N; u++) {
      for (let p = this.off[u]; p < this.off[u + 1]; p++) {
        const v = this.to[p]
        const [x, y] = local.toXY((this.lon[u] + this.lon[v]) / 2, (this.lat[u] + this.lat[v]) / 2)
        const r = Math.hypot(x, y)
        radii.forEach((R, k) => { if (r <= R) sums[k] += this.len[p] / 1000 })
      }
    }
    return sums
  }
}
