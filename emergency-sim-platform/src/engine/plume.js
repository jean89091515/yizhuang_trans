/**
 * 高斯烟羽扩散模型（论文式(1)(2)，Step9 compute_plume_grid 的逐项移植）
 *   C(x,y) = Q/(2π u σy σz) · exp(-y²/2σy²) · [exp(-(z-H)²/2σz²) + exp(-(z+H)²/2σz²)],  z = 0
 *   σy = a·x/√(1+b·x),  σz = c·x/√(1+d·x)   （Briggs 城市条件经验式）
 */
import { contours } from 'd3-contour'
import { makeLocal } from './geo.js'

const SIGMA = {
  A: [0.32, 0.0004, 0.24, 0.001],
  B: [0.22, 0.0004, 0.16, 0.001],
  C: [0.16, 0.0004, 0.11, 0.001],
  D: [0.11, 0.0004, 0.08, 0.0015],
  E: [0.08, 0.0004, 0.06, 0.003],
  F: [0.06, 0.0004, 0.04, 0.003],
}

export function sigmas(x, stability) {
  const [a, b, c, d] = SIGMA[stability] || SIGMA.D
  return [Math.max((a * x) / Math.sqrt(1 + b * x), 0.1), Math.max((c * x) / Math.sqrt(1 + d * x), 0.1)]
}

/** 下风向 xw、横风向 yw (m) 处地面浓度 (mg/m³) */
export function concentration(xw, yw, Q, u, H, stability) {
  if (xw <= 10) return 0 // 与 Step9 一致：仅下风向 >10 m 计算
  const [sy, sz] = sigmas(xw, stability)
  const g = Math.exp(-0.5 * (H / sz) ** 2)
  const c = (Q / (2 * Math.PI * u * sy * sz)) * Math.exp(-0.5 * (yw / sy) ** 2) * (g + g)
  return c > 0 ? c : 0
}

/**
 * 计算以事故点为中心的浓度网格。
 * 网格行 i 对应 y = -extent + i·cell（自南向北），列 j 对应 x = -extent + j·cell（自西向东）。
 */
export function computePlume(params) {
  const { incident, leakRateKgMin, windSpeed, windDir, stability, releaseHeightM } = params
  const extent = params.plume.extentM
  const cell = params.plume.cellM
  const Q = (leakRateKgMin * 1e6) / 60 // mg/s
  const u = Math.max(windSpeed, 0.5)
  const H = releaseHeightM ?? 2.0
  const plumeDir = (((windDir + 180) % 360) * Math.PI) / 180 // 风的去向
  const sinA = Math.sin(plumeDir)
  const cosA = Math.cos(plumeDir)
  const n = Math.round((2 * extent) / cell) + 1
  const conc = new Float32Array(n * n)
  let max = 0
  for (let i = 0; i < n; i++) {
    const y = -extent + i * cell
    for (let j = 0; j < n; j++) {
      const x = -extent + j * cell
      const xw = x * sinA + y * cosA
      if (xw <= 10) continue
      const yw = x * cosA - y * sinA
      const c = concentration(xw, yw, Q, u, H, stability)
      conc[i * n + j] = c
      if (c > max) max = c
    }
  }
  const local = makeLocal(incident.lon, incident.lat)
  return {
    n, cell, extent, conc, max, local,
    plumeDirDeg: (windDir + 180) % 360,
    Q, u, H, stability,
    /** 最近网格点浓度（与 Step11 compute_risk_exposure 的 argmin 取值一致） */
    concAt(lon, lat) {
      const [x, y] = local.toXY(lon, lat)
      const j = Math.round((x + extent) / cell)
      const i = Math.round((y + extent) / cell)
      if (i < 0 || j < 0 || i >= n || j >= n) return 0
      return conc[i * n + j]
    },
  }
}

/** 网格坐标(d3-contour) → 经纬度 GeoJSON 坐标 */
export function gridRingsToLonLat(geometry, grid) {
  const { cell, extent, local } = grid
  const conv = ([gx, gy]) => {
    const x = -extent + (gx - 0.5) * cell
    const y = -extent + (gy - 0.5) * cell
    const [lon, lat] = local.toLL(x, y)
    return [Math.round(lon * 1e6) / 1e6, Math.round(lat * 1e6) / 1e6]
  }
  return {
    type: 'MultiPolygon',
    coordinates: geometry.coordinates.map((poly) => poly.map((ring) => ring.map(conv))),
  }
}

/** 浓度等值线面（≥ threshold 的区域），返回 GeoJSON MultiPolygon（经纬度） */
export function plumeContours(plume, thresholds) {
  const gen = contours().size([plume.n, plume.n]).smooth(true)
  return thresholds.map((t) => {
    const g = gen.thresholds([t])(plume.conc)[0]
    return { threshold: t, geometry: gridRingsToLonLat(g, plume), empty: g.coordinates.length === 0 }
  })
}

/**
 * 浓度场栅格（供前端渲染热力图）：裁剪到浓度 ≥ minVal 的外包范围，尽量保持 50 m 原始分辨率。
 * values 行自北向南、列自西向东；bounds 为像元外边界（WGS84）。
 */
export function plumeRaster(plume, maxSize = 400, minVal = 0.05) {
  const { n, conc, cell, extent, local } = plume
  let i0 = n, i1 = -1, j0 = n, j1 = -1
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (conc[i * n + j] >= minVal) {
        if (i < i0) i0 = i
        if (i > i1) i1 = i
        if (j < j0) j0 = j
        if (j > j1) j1 = j
      }
    }
  }
  if (i1 < 0) return null
  const padC = 2
  i0 = Math.max(0, i0 - padC); j0 = Math.max(0, j0 - padC)
  i1 = Math.min(n - 1, i1 + padC); j1 = Math.min(n - 1, j1 + padC)
  const step = Math.max(1, Math.ceil(Math.max(i1 - i0 + 1, j1 - j0 + 1) / maxSize))
  const w = Math.floor((j1 - j0) / step) + 1
  const h = Math.floor((i1 - i0) / step) + 1
  const values = new Array(w * h)
  for (let r = 0; r < h; r++) {
    const i = i1 - r * step // 北 → 南
    for (let c = 0; c < w; c++) values[r * w + c] = Math.round(conc[i * n + j0 + c * step] * 1000) / 1000
  }
  const half = (step * cell) / 2
  const xW = -extent + j0 * cell - half
  const xE = -extent + (j0 + (w - 1) * step) * cell + half
  const yN = -extent + i1 * cell + half
  const yS = -extent + (i1 - (h - 1) * step) * cell - half
  const [west, north] = local.toLL(xW, yN)
  const [east, south] = local.toLL(xE, yS)
  return { width: w, height: h, values, max: plume.max, bounds: { west, south, east, north } }
}
