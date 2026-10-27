/**
 * ERPG 危险分区 + 受影响人口统计（论文 3.1.2 节；Step11 load_erpg_zone_populations）
 *
 * 分区（buffered，论文基准场景实际采用的“策略2”）:
 *   ERPG-3 = 等值线(≥20 mg/m³) 外扩 500 m
 *   ERPG-2 = 等值线(≥3 mg/m³) 外扩 1500 m − ERPG-3
 *   ERPG-1 = 等值线(≥1 mg/m³) 外扩 3000 m − 等值线(≥3) 外扩 1500 m
 * 外扩通过浓度网格上的欧氏距离变换实现（误差 ≤ 半个网格 25 m）。
 */
import { contours } from 'd3-contour'
import { gridRingsToLonLat } from './plume.js'
import { ZONE_KEYS, SECTOR_NAMES } from './defaults.js'
import { bearingDeg } from './geo.js'

const INF = 1e20

/** Felzenszwalb–Huttenlocher 一维平方距离变换 */
function edt1d(f, n, d, v, z) {
  let k = 0
  v[0] = 0
  z[0] = -INF
  z[1] = INF
  for (let q = 1; q < n; q++) {
    let s = (f[q] + q * q - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
    while (s <= z[k]) {
      k--
      s = (f[q] + q * q - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
    }
    k++
    v[k] = q
    z[k] = s
    z[k + 1] = INF
  }
  k = 0
  for (let q = 0; q < n; q++) {
    while (z[k + 1] < q) k++
    d[q] = (q - v[k]) * (q - v[k]) + f[v[k]]
  }
}

/** 二维欧氏距离变换：mask=1 处距离为 0；返回以“网格数”为单位的距离 */
export function distanceTransform(mask, n) {
  const g = new Float64Array(n * n)
  for (let i = 0; i < n * n; i++) g[i] = mask[i] ? 0 : INF
  const f = new Float64Array(n)
  const d = new Float64Array(n)
  const v = new Int32Array(n)
  const z = new Float64Array(n + 1)
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) f[i] = g[i * n + j]
    edt1d(f, n, d, v, z)
    for (let i = 0; i < n; i++) g[i * n + j] = d[i]
  }
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) f[j] = g[i * n + j]
    edt1d(f, n, d, v, z)
    for (let j = 0; j < n; j++) g[i * n + j] = Math.sqrt(d[j])
  }
  return g
}

/**
 * 计算分区：返回各阈值的距离场（m）与分区判定函数。
 * mode: buffered | contour（缓冲距离取 0）
 */
export function computeZones(plume, thresholds, buffersM, mode = 'buffered') {
  const { n, cell, extent, conc } = plume
  const levels = { erpg3: thresholds.ERPG3, erpg2: thresholds.ERPG2, erpg1: thresholds.ERPG1 }
  const buf = mode === 'contour' ? { erpg3: 0, erpg2: 0, erpg1: 0 } : buffersM
  const dist = {}
  const cells = {}
  for (const z of ZONE_KEYS) {
    const mask = new Uint8Array(n * n)
    let cnt = 0
    for (let i = 0; i < n * n; i++) if (conc[i] >= levels[z]) { mask[i] = 1; cnt++ }
    cells[z] = cnt
    const d = distanceTransform(mask, n)
    for (let i = 0; i < n * n; i++) d[i] = cnt ? d[i] * cell : INF
    dist[z] = d
  }
  // contour 模式下，等值线以内（距离=0）才算入区；buffered 模式按缓冲距离
  const within = (z, idx) => (buf[z] > 0 ? dist[z][idx] <= buf[z] : dist[z][idx] === 0)
  function classifyIdx(idx) {
    if (within('erpg3', idx)) return 3
    if (within('erpg2', idx)) return 2
    if (within('erpg1', idx)) return 1
    return 0
  }
  return {
    mode, buffers: buf, levels, dist, cells,
    /** 局部米制坐标 → 分区编号 3/2/1/0 */
    classifyXY(x, y) {
      const j = Math.round((x + extent) / cell)
      const i = Math.round((y + extent) / cell)
      if (i < 0 || j < 0 || i >= n || j >= n) return 0
      return classifyIdx(i * n + j)
    },
  }
}

/** 分区多边形（经纬度 GeoJSON），供地图绘制 */
export function zonePolygons(plume, zones) {
  const { n } = plume
  const gen = contours().size([n, n]).smooth(true)
  const out = {}
  for (const z of ZONE_KEYS) {
    const b = zones.buffers[z]
    const d = zones.dist[z]
    const vals = new Float64Array(n * n)
    for (let i = 0; i < n * n; i++) vals[i] = -Math.min(d[i], 1e9)
    const g = gen.thresholds([-(b > 0 ? b : 0.5 * plume.cell)])(vals)[0]
    out[z] = gridRingsToLonLat(g, plume)
  }
  return out
}

// ---------------------------------------------------------------------
// 人口数据
// ---------------------------------------------------------------------

/** 解码 population.json（游程编码标签栅格） */
export function loadPopulation(json) {
  const { grid, blocks, cells_rle: rle } = json
  const labels = new Int32Array(grid.nx * grid.ny)
  let p = 0
  for (let k = 0; k < rle.length; k += 2) {
    labels.fill(rle[k], p, p + rle[k + 1])
    p += rle[k + 1]
  }
  const pops = Float64Array.from(blocks)
  const blockCells = new Int32Array(pops.length)
  for (let i = 0; i < labels.length; i++) blockCells[labels[i]]++
  return { grid, labels, pops, blockCells, age: json.age_structure, meta: json.meta }
}

/**
 * 统计各分区/圆形区受影响人口，并按 8 方位扇区汇总（用于生成疏散起点/就地避难需求点）。
 * mode=intersect：地块与区域相交即计其全部人口（论文 gpd.clip 口径，跨区地块可重复计数）
 * mode=area：按地块落入区域的面积比例分摊
 */
export function aggregatePopulation(pop, zones, plume, opts) {
  const { grid, labels, pops, blockCells } = pop
  const { local, extent } = plume
  const mode = opts.mode || 'intersect'
  const circleR = opts.circles || [1000, 3000, 5000]
  // 只扫描浓度网格覆盖范围内的人口栅格
  const [w, s] = local.toLL(-extent, -extent)
  const [e, nn] = local.toLL(extent, extent)
  const c0 = Math.max(0, Math.floor((w - grid.lon0) / grid.dlon))
  const c1 = Math.min(grid.nx - 1, Math.ceil((e - grid.lon0) / grid.dlon))
  const r0 = Math.max(0, Math.floor((grid.lat0 - nn) / grid.dlat))
  const r1 = Math.min(grid.ny - 1, Math.ceil((grid.lat0 - s) / grid.dlat))

  const zoneHits = { erpg3: new Map(), erpg2: new Map(), erpg1: new Map() }
  const circleHits = circleR.map(() => new Map())
  const zkey = [null, 'erpg1', 'erpg2', 'erpg3']
  const { n: pn, cell: pc, conc } = plume
  const concXY = (x, y) => {
    const j = Math.round((x + extent) / pc)
    const i = Math.round((y + extent) / pc)
    return i < 0 || j < 0 || i >= pn || j >= pn ? 0 : conc[i * pn + j]
  }
  const add = (map, b, x, y, cz = 0) => {
    let h = map.get(b)
    if (!h) { h = { cells: 0, sx: 0, sy: 0, sc: 0 }; map.set(b, h) }
    h.cells++; h.sx += x; h.sy += y; h.sc += cz
  }
  for (let r = r0; r <= r1; r++) {
    const lat = grid.lat0 - (r + 0.5) * grid.dlat
    for (let c = c0; c <= c1; c++) {
      const b = labels[r * grid.nx + c]
      if (b === 0) continue
      const lon = grid.lon0 + (c + 0.5) * grid.dlon
      const [x, y] = local.toXY(lon, lat)
      const z = zones.classifyXY(x, y)
      if (z) add(zoneHits[zkey[z]], b, x, y, concXY(x, y))
      const rr = Math.hypot(x, y)
      for (let k = 0; k < circleR.length; k++) if (rr <= circleR[k]) add(circleHits[k], b, x, y)
    }
  }
  const weight = (b, h) => (mode === 'area' ? h.cells / blockCells[b] : 1)
  const children = pop.age?.children ?? 0.12
  const elderly = pop.age?.elderly ?? 0.15

  const zonesOut = {}
  const sectors = []
  for (const z of ZONE_KEYS) {
    let total = 0
    const sec = Array.from({ length: 8 }, () => ({ pop: 0, sx: 0, sy: 0, sc: 0 }))
    for (const [b, h] of zoneHits[z]) {
      const p = pops[b] * weight(b, h)
      if (p <= 0) continue
      total += p
      const cx = h.sx / h.cells
      const cy = h.sy / h.cells
      const k = Math.floor(((bearingDeg(cx, cy) + 22.5) % 360) / 45)
      sec[k].pop += p; sec[k].sx += p * cx; sec[k].sy += p * cy; sec[k].sc += p * (h.sc / h.cells)
    }
    zonesOut[z] = {
      total: Math.round(total),
      children: total * children,
      elderly: total * elderly,
      working: total * (1 - children - elderly),
      blocks: zoneHits[z].size,
    }
    sec.forEach((q, k) => {
      if (q.pop <= 0) return
      const [lon, lat] = local.toLL(q.sx / q.pop, q.sy / q.pop)
      // rho：该扇区人口加权平均浓度（各地块落区网格的平均浓度），作为动态风险暴露系数
      sectors.push({ zone: z, sector: k, sectorName: SECTOR_NAMES[k], pop: q.pop, lon, lat, rho: q.sc / q.pop })
    })
  }
  const circles = {}
  circleR.forEach((R, k) => {
    let t = 0
    for (const [b, h] of circleHits[k]) t += pops[b] * weight(b, h)
    circles[`r${R}`] = Math.round(t)
  })
  return { zones: zonesOut, sectors, circles, mode }
}
