/**
 * 地图显示图层：底图配置与 basemap.json（分级道路、地铁）解码、路网状态计算。
 * 这些图层只用于显示，不参与计算（计算用 road_network.json）。
 */

const AMAP_ROAD = 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}'
const DARK_FILTER = 'invert(1) hue-rotate(185deg) brightness(0.62) contrast(1.05) saturate(0.55)'

/** 底图列表：config.js 中 map.basemaps；未配置时由旧版 map.tileUrl 生成 */
export function getBasemaps() {
  const m = (window.EMERGENCY_SIM_CONFIG || {}).map || {}
  let list = Array.isArray(m.basemaps) && m.basemaps.length ? m.basemaps : [
    { id: 'default', name: '在线底图', url: m.tileUrl || AMAP_ROAD, subdomains: m.subdomains, darkFilter: m.darkFilter !== false },
  ]
  list = list.map((b, i) => ({
    id: b.id || `bm${i}`,
    name: b.name || `底图${i + 1}`,
    url: b.url || '',
    overlayUrl: b.overlayUrl || '',
    subdomains: b.subdomains || m.subdomains || ['1', '2', '3', '4'],
    maxNativeZoom: b.maxNativeZoom ?? 18,
    filter: b.filter ?? (b.darkFilter ? DARK_FILTER : 'none'),
  }))
  if (!list.some((b) => !b.url)) list.push({ id: 'none', name: '无底图', url: '', overlayUrl: '', filter: 'none' })
  return list
}

// 与 tools/export_platform_data.py 的 DISPLAY_ROAD_CLASSES 顺序一致
export const ROAD_CLASSES = [
  { key: 'motorway', name: '高速公路', color: '#5ab0ff', w: 2.6, minZoom: 9, glow: true, tier: 0 },
  { key: 'motorway_link', name: '高速匝道', color: '#5ab0ff', w: 1.1, minZoom: 13, tier: 0 },
  { key: 'trunk', name: '快速路', color: '#4b9ff0', w: 2.2, minZoom: 9, glow: true, tier: 0 },
  { key: 'trunk_link', name: '快速路匝道', color: '#4b9ff0', w: 1.0, minZoom: 13, tier: 0 },
  { key: 'primary', name: '主干路', color: '#3f8bd6', w: 1.7, minZoom: 10.5, tier: 1 },
  { key: 'primary_link', name: '主干路连接线', color: '#3f8bd6', w: 0.9, minZoom: 14, tier: 1 },
  { key: 'secondary', name: '次干路', color: '#3577ba', w: 1.3, minZoom: 11.5, tier: 1 },
  { key: 'secondary_link', name: '次干路连接线', color: '#3577ba', w: 0.8, minZoom: 14, tier: 1 },
  { key: 'tertiary', name: '支路', color: '#2d659f', w: 1.0, minZoom: 12.5, tier: 2 },
  { key: 'tertiary_link', name: '支路连接线', color: '#2d659f', w: 0.7, minZoom: 14, tier: 2 },
  { key: 'residential', name: '街坊路', color: '#27527f', w: 0.8, minZoom: 13.5, tier: 2 },
  { key: 'unclassified', name: '其他道路', color: '#27527f', w: 0.8, minZoom: 13.5, tier: 2 },
]
/** 道路名称标注的最小缩放级别（按道路等级） */
export const LABEL_MIN_ZOOM = { motorway: 11.5, trunk: 11.5, primary: 12.5, secondary: 13.5 }

export function decodeLine(d) {
  const out = new Array(d.length / 2)
  let x = 0
  let y = 0
  for (let i = 0; i < d.length; i += 2) {
    x += d[i]
    y += d[i + 1]
    out[i / 2] = [x / 1e5, y / 1e5]
  }
  return out
}

/** basemap.json → { roads: [{cls, name, coords}], subway: [{name, color, coords}], stations, totalKm } */
export function decodeBasemap(raw) {
  if (!raw) return null
  const names = raw.names || []
  const roads = (raw.roads || []).map(([cls, ni, d]) => ({ cls: Math.min(cls, ROAD_CLASSES.length - 1), name: ni >= 0 ? names[ni] : null, coords: decodeLine(d) }))
  const subway = (raw.subway || []).map((s) => ({ name: s.name, color: s.color || '#7fb7ff', coords: decodeLine(s.d) }))
  const stations = raw.subway_stations || []
  let totalKm = 0
  for (const r of roads) {
    r.lenM = lineLengthM(r.coords)
    r.bb = bbox(r.coords)
    totalKm += r.lenM / 1000
  }
  return { roads, subway, stations, totalKm, meta: raw.meta || {} }
}

const KY = 110540
const kxAt = (lat) => 111320 * Math.cos((lat * Math.PI) / 180)

function bbox(cs) {
  const bb = [Infinity, Infinity, -Infinity, -Infinity]
  for (const [x, y] of cs) {
    if (x < bb[0]) bb[0] = x
    if (y < bb[1]) bb[1] = y
    if (x > bb[2]) bb[2] = x
    if (y > bb[3]) bb[3] = y
  }
  return bb
}

export function lineLengthM(cs) {
  let s = 0
  for (let i = 1; i < cs.length; i++) {
    const kx = kxAt(cs[i][1])
    s += Math.hypot((cs[i][0] - cs[i - 1][0]) * kx, (cs[i][1] - cs[i - 1][1]) * KY)
  }
  return s
}

/**
 * 路网状态（与引擎一致）：距事故点 < 封闭半径 → 封闭；< 拥堵半径 → BPR 拥堵，
 * 行程时间系数 f = (1 + α·(v/c)^β)·(1 + (Rc − r)/Rc)。
 * 道路按约 80 m 细分后逐段判定（长路段只着色圈内部分），相邻同级合并。
 * 返回 [{ road, level: 'closed'|'heavy'|'medium'|'light', coords, lenM, fmin, fmax }]
 */
export function roadStatus(basemap, res) {
  if (!basemap?.roads?.length || !res?.roads) return []
  const { lon, lat } = res.params.incident
  const R = res.roads.closureRadiusM
  const Rc = res.roads.congestionRadiusM
  const { bprAlpha = 0.15, bprBeta = 4, vc = 0.8 } = res.params.roads || {}
  const bpr = 1 + bprAlpha * Math.pow(vc, bprBeta)
  const kx = kxAt(lat)
  const padY = Rc / KY
  const padX = Rc / kx
  const dist = (x, y) => Math.hypot((x - lon) * kx, (y - lat) * KY)
  const out = []
  for (const road of basemap.roads) {
    const bb = road.bb
    if (bb[0] > lon + padX || bb[2] < lon - padX || bb[1] > lat + padY || bb[3] < lat - padY) continue // 包围盒粗筛
    const cs = road.coords
    let cur = null
    for (let i = 1; i < cs.length; i++) {
      const [ax, ay] = cs[i - 1]
      const [bx, by] = cs[i]
      const segM = Math.hypot((bx - ax) * kx, (by - ay) * KY)
      if (Math.min(dist(ax, ay), dist(bx, by)) > Rc + segM) { cur = null; continue }
      const n = Math.max(1, Math.ceil(segM / 80))
      for (let k = 0; k < n; k++) {
        const d = dist(ax + ((bx - ax) * (k + 0.5)) / n, ay + ((by - ay) * (k + 0.5)) / n)
        if (d >= Rc) { cur = null; continue }
        const f = d < R ? Infinity : bpr * (1 + (Rc - d) / Rc)
        const level = d < R ? 'closed' : f >= 1.5 ? 'heavy' : f >= 1.25 ? 'medium' : 'light'
        const p1 = [ax + ((bx - ax) * (k + 1)) / n, ay + ((by - ay) * (k + 1)) / n]
        if (cur && cur.level === level) {
          cur.coords.push(p1)
        } else {
          cur = { road, level, coords: [[ax + ((bx - ax) * k) / n, ay + ((by - ay) * k) / n], p1], lenM: 0, fmin: f, fmax: f }
          out.push(cur)
        }
        cur.lenM += segM / n
        cur.fmin = Math.min(cur.fmin, f)
        cur.fmax = Math.max(cur.fmax, f)
      }
    }
  }
  return out
}

export const STATUS_STYLE = {
  closed: { color: '#ff3b4f', name: '封闭', glow: true },
  heavy: { color: '#ff7a33', name: '严重拥堵' },
  medium: { color: '#ffae3d', name: '拥堵' },
  light: { color: '#ffe066', name: '缓行' },
}

/** 估算标注文字宽度（px，12px 字号） */
export function textWidth(s, size = 12) {
  let w = 0
  for (const ch of s) w += ch.charCodeAt(0) > 255 ? size + 1 : size * 0.62
  return w
}

/** 道路名称标注候选：每条命名路段按长度取中点与局部走向 */
export function labelCandidates(basemap) {
  const out = []
  if (!basemap) return out
  for (const r of basemap.roads) {
    const key = ROAD_CLASSES[r.cls].key
    const minZoom = LABEL_MIN_ZOOM[key]
    if (!r.name || minZoom === undefined || r.lenM < 150) continue
    const half = r.lenM / 2
    let acc = 0
    for (let i = 1; i < r.coords.length; i++) {
      const a = r.coords[i - 1]
      const b = r.coords[i]
      const seg = lineLengthM([a, b])
      if (acc + seg >= half || i === r.coords.length - 1) {
        const u = seg > 0 ? Math.min(1, (half - acc) / seg) : 0.5
        out.push({ name: r.name, cls: r.cls, minZoom, lenM: r.lenM, a, b, mid: [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u] })
        break
      }
      acc += seg
    }
  }
  out.sort((p, q) => p.cls - q.cls || q.lenM - p.lenM)
  return out
}
