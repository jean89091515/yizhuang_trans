<template>
  <div ref="el" class="map" :class="{ 'dark-tiles': mapCfg.darkFilter !== false, 'pick-mode': state.pickMode }"></div>
</template>

<script setup>
/**
 * 地图图层（Leaflet）。数据坐标均为 WGS84，按配置转换为底图坐标系（高德瓦片为 GCJ-02）。
 * 若平台已有统一地图组件（如高德 JS API），可参照本文件的图层划分与样式迁移。
 */
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { state, result, staticData, setIncidentFromMap } from '../store.js'
import { wgs84ToGcj02, gcj02ToWgs84, SUPPLY_CATEGORIES, VEHICLE_MODES } from '../engine/index.js'

const mapCfg = (window.EMERGENCY_SIM_CONFIG || {}).map || {}
const isGcj = (mapCfg.coord || 'gcj02') === 'gcj02'
const el = ref(null)
let map = null
const layers = {}
let vehicleState = null
let originMarkers = []
let fitDone = false

const ll = (lon, lat) => {
  const [x, y] = isGcj ? wgs84ToGcj02(lon, lat) : [lon, lat]
  return L.latLng(y, x)
}
const llArr = (path) => path.map(([lon, lat]) => ll(lon, lat))
const geo = (gj, style, opts = {}) => L.geoJSON(gj, { coordsToLatLng: (c) => ll(c[0], c[1]), style, ...opts })

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
const tip = (html) => ({ className: 'sim-tip', direction: 'top', offset: [0, -8], sticky: false, html })

// ---------------- 图标 ----------------
function icon(kind, size = 22) {
  const s = size
  const svg = {
    fire: `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><rect x="2" y="2" width="20" height="20" rx="3" fill="#ff8a3d" stroke="#fff" stroke-width="1.5"/><path d="M12 5c1 3 4 4 4 8a4 4 0 0 1-8 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-4 0-7z" fill="#fff"/></svg>`,
    warehouse: `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><rect x="2" y="2" width="20" height="20" rx="3" fill="#d4a017" stroke="#fff" stroke-width="1.5"/><path d="M5 10l7-4 7 4v8H5z" fill="none" stroke="#fff" stroke-width="1.8"/><path d="M9 18v-5h6v5" stroke="#fff" stroke-width="1.6" fill="none"/></svg>`,
    relay: `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><circle cx="12" cy="12" r="10" fill="#7b4dff" stroke="#fff" stroke-width="1.5"/><path d="M8 7v10M16 7v10M8 12h8" stroke="#fff" stroke-width="2.2"/></svg>`,
    rescue: `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><circle cx="12" cy="12" r="10" fill="#ff4d4f" stroke="#fff" stroke-width="1.5"/><circle cx="12" cy="12" r="5" fill="none" stroke="#fff" stroke-width="2"/><circle cx="12" cy="12" r="1.8" fill="#fff"/></svg>`,
    hospital: `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><rect x="2" y="2" width="20" height="20" rx="10" fill="#fff" stroke="#ff4d4f" stroke-width="2"/><path d="M12 6v12M6 12h12" stroke="#ff4d4f" stroke-width="3.4"/></svg>`,
    shelter: `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><rect x="2" y="2" width="20" height="20" rx="3" fill="#2fbf71" stroke="#fff" stroke-width="1.5"/><path d="M5 18L12 6l7 12zM12 6v12" fill="none" stroke="#fff" stroke-width="1.8"/></svg>`,
    shelterDemand: `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><path d="M12 2l10 18H2z" fill="#ffd23f" stroke="#fff" stroke-width="1.5"/><path d="M12 9v5M12 16v1.5" stroke="#5a3d00" stroke-width="2.2"/></svg>`,
    subway: `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><circle cx="12" cy="12" r="10" fill="#2f7bff" stroke="#fff" stroke-width="1.5"/><path d="M7 17V7l5 6 5-6v10" fill="none" stroke="#fff" stroke-width="2"/></svg>`,
  }[kind]
  return L.divIcon({ className: 'fac-ico', html: svg, iconSize: [s, s], iconAnchor: [s / 2, s / 2] })
}

const incidentIcon = L.divIcon({
  className: 'inc-ico',
  html: `<div class="inc-wrap"><span class="pulse"></span><span class="pulse p2"></span>
    <svg viewBox="0 0 32 44" width="32" height="44"><defs><radialGradient id="pin-g" cx="0.4" cy="0.35" r="0.7"><stop offset="0" stop-color="#ff8a8a"/><stop offset="1" stop-color="#e01e1e"/></radialGradient></defs>
    <path d="M16 1C8 1 2 7 2 15c0 10 14 27 14 27s14-17 14-27C30 7 24 1 16 1z" fill="url(#pin-g)" stroke="#fff" stroke-width="1.5"/><circle cx="16" cy="15" r="5.5" fill="#fff"/></svg></div>`,
  iconSize: [32, 44],
  iconAnchor: [16, 42],
})

// ---------------- 初始化 ----------------
onMounted(() => {
  const [clon, clat] = mapCfg.center || [116.494, 39.745]
  map = L.map(el.value, {
    zoomControl: false, attributionControl: false, preferCanvas: false,
    minZoom: mapCfg.minZoom ?? 9, maxZoom: mapCfg.maxZoom ?? 18,
    center: ll(clon, clat), zoom: mapCfg.zoom ?? 13, zoomSnap: 0.25,
  })
  if (mapCfg.tileUrl) {
    L.tileLayer(mapCfg.tileUrl, { subdomains: mapCfg.subdomains || ['1', '2', '3', '4'], maxZoom: 18, maxNativeZoom: 18 }).addTo(map)
  }
  const panes = { boundary: 340, zones: 360, plume: 370, contours: 380, routes: 420, flows: 425, nodes: 450, vehicles: 460, incident: 480 }
  for (const [k, z] of Object.entries(panes)) { map.createPane(k); map.getPane(k).style.zIndex = z }
  map.getPane('zones').style.mixBlendMode = 'screen'
  layers.canvasVeh = L.canvas({ pane: 'vehicles', padding: 0.3 })
  for (const k of ['boundary', 'hazard', 'supply', 'evac', 'vehicles', 'incident']) layers[k] = L.layerGroup().addTo(map)
  map.on('click', (e) => {
    if (!state.pickMode) return
    const [lon, lat] = isGcj ? gcj02ToWgs84(e.latlng.lng, e.latlng.lat) : [e.latlng.lng, e.latlng.lat]
    setIncidentFromMap(lon, lat)
  })
  drawBoundary()
  drawIncident()
  if (result.value) rebuild()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => { window.removeEventListener('resize', onResize); map?.remove() })
function onResize() { map?.invalidateSize() }

function panelPadding() {
  const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080)
  const lp = state.leftCollapsed ? 80 : 600
  const rp = state.rightCollapsed ? 80 : 600
  return { paddingTopLeft: [lp * s, 170 * s], paddingBottomRight: [rp * s, 140 * s] }
}

// ---------------- 静态图层 ----------------
function drawBoundary() {
  const b = staticData.value?.boundary
  if (!b || !map) return
  layers.boundary.clearLayers()
  geo(b, () => ({ pane: 'boundary', color: '#6fb6ff', weight: 7, opacity: 0.18, fill: false })).addTo(layers.boundary)
  geo(b, () => ({ pane: 'boundary', color: '#4f9dff', weight: 2, opacity: 0.95, fillColor: '#2f6fe0', fillOpacity: 0.26 }))
    .bindTooltip('亦庄控规界', { className: 'sim-tip', sticky: true }).addTo(layers.boundary)
}

function drawIncident() {
  if (!map) return
  layers.incident.clearLayers()
  const inc = state.params.incident
  L.marker(ll(inc.lon, inc.lat), { icon: incidentIcon, pane: 'incident', interactive: true })
    .bindTooltip(`<b>${esc(inc.name || '事故点')}</b><br/>${inc.lon.toFixed(5)}°E, ${inc.lat.toFixed(5)}°N<br/>${esc(state.params.gas)}泄漏 ${state.params.leakRateKgMin} kg/min`, { className: 'sim-tip', direction: 'top', offset: [0, -40] })
    .addTo(layers.incident)
}

// ---------------- 灾害场景 ----------------
function plumeCanvas(r) {
  const c = document.createElement('canvas')
  c.width = r.width
  c.height = r.height
  const ctx = c.getContext('2d')
  const img = ctx.createImageData(r.width, r.height)
  const stops = [
    [Math.log10(0.05), [255, 240, 160, 0]],
    [Math.log10(0.5), [255, 230, 120, 90]],
    [Math.log10(1), [255, 210, 63, 140]],
    [Math.log10(3), [255, 138, 61, 175]],
    [Math.log10(20), [255, 60, 60, 205]],
    [Math.log10(100), [200, 0, 60, 230]],
  ]
  for (let i = 0; i < r.values.length; i++) {
    const v = r.values[i]
    if (v < 0.05) continue
    const lv = Math.log10(v)
    let k = 0
    while (k < stops.length - 2 && lv > stops[k + 1][0]) k++
    const [a, ca] = stops[k]
    const [b, cb] = stops[k + 1]
    const f = Math.max(0, Math.min(1, (lv - a) / (b - a)))
    for (let ch = 0; ch < 4; ch++) img.data[i * 4 + ch] = ca[ch] + (cb[ch] - ca[ch]) * f
  }
  ctx.putImageData(img, 0, 0)
  return c.toDataURL()
}

function drawHazard(res) {
  const g = layers.hazard
  g.clearLayers()
  const inc = res.params.incident
  const zp = res.zones.populations
  const zoneStyle = {
    erpg1: { color: '#ffd23f', fill: 0.10, dash: '6 6', name: 'ERPG-1 影响区' },
    erpg2: { color: '#ff8a3d', fill: 0.16, dash: '6 4', name: 'ERPG-2 警戒区' },
    erpg3: { color: '#ff4d4f', fill: 0.26, dash: null, name: 'ERPG-3 核心危险区' },
  }
  for (const z of ['erpg1', 'erpg2', 'erpg3']) {
    const poly = res.zones.polygons[z]
    if (!poly || !poly.coordinates.length) continue
    const st = zoneStyle[z]
    const lyr = geo(poly, () => ({ pane: 'zones', color: st.color, weight: 1.6, dashArray: st.dash, fillColor: st.color, fillOpacity: st.fill }))
    lyr.bindTooltip(`<b>${st.name}</b><br/>人口 ${zp[z].total.toLocaleString()} 人（${zp[z].blocks} 个地块）`, { className: 'sim-tip', sticky: true })
    lyr.addTo(g)
    const b = lyr.getBounds()
    if (b.isValid()) {
      const south = z === 'erpg3'
      L.tooltip({ permanent: true, direction: south ? 'bottom' : 'top', className: 'map-label zone-label', offset: [0, 0] })
        .setLatLng(L.latLng(south ? b.getSouth() : b.getNorth(), b.getCenter().lng))
        .setContent(`<span style="color:${st.color}">${st.name.split(' ')[0]}</span> ${zp[z].total >= 1e4 ? (zp[z].total / 1e4).toFixed(1) + '万' : zp[z].total.toLocaleString()}人`)
        .addTo(g)
    }
  }
  // 浓度热力
  if (res.plume.raster) {
    const r = res.plume.raster
    const sw = ll(r.bounds.west, r.bounds.south)
    const ne = ll(r.bounds.east, r.bounds.north)
    L.imageOverlay(plumeCanvas(r), L.latLngBounds(sw, ne), { pane: 'plume', opacity: 0.95, interactive: false, className: 'plume-img' }).addTo(g)
  }
  // ERPG 原始等值线
  const cstyle = { 0.5: ['#fff3b0', 1, '2 4'], 1: ['#ffd23f', 1.6], 3: ['#ff8a3d', 1.8], 20: ['#ff4d4f', 2.2] }
  for (const c of res.plume.contours) {
    if (c.empty) continue
    const [color, weight, dash] = cstyle[c.threshold] || ['#fff', 1]
    geo(c.geometry, () => ({ pane: 'contours', color, weight, dashArray: dash, fill: false }))
      .bindTooltip(`浓度等值线 ${c.threshold} mg/m³`, { className: 'sim-tip', sticky: true }).addTo(g)
  }
  // 封闭/拥堵圈
  const c0 = ll(inc.lon, inc.lat)
  L.circle(c0, { pane: 'contours', radius: res.roads.closureRadiusM, color: '#ff4d4f', weight: 2, dashArray: '8 6', fill: true, fillColor: '#ff4d4f', fillOpacity: 0.05 })
    .bindTooltip(`道路封闭区 ${res.roads.closureRadiusM} m<br/>封闭道路 ${res.roads.closedKm.toFixed(1)} km`, { className: 'sim-tip', sticky: true }).addTo(g)
  L.circle(c0, { pane: 'contours', radius: res.roads.congestionRadiusM, color: '#ff8a3d', weight: 1.4, dashArray: '3 7', fill: false, interactive: false }).addTo(g)
  // 风向箭头（烟羽去向）
  const reach = Math.max(1500, (res.plume.reach.erpg1.maxDistM || 1000) * 1.25)
  const th = (res.plume.plumeDirDeg * Math.PI) / 180
  const kx = 111320 * Math.cos((inc.lat * Math.PI) / 180)
  const tip0 = [inc.lon + (Math.sin(th) * reach) / kx, inc.lat + (Math.cos(th) * reach) / 110540]
  L.polyline([c0, ll(...tip0)], { pane: 'contours', color: '#bfe9ff', weight: 2, dashArray: '10 8', className: 'flow-line', interactive: false }).addTo(g)
  L.marker(ll(...tip0), {
    pane: 'contours', interactive: false,
    icon: L.divIcon({ className: 'wind-arrow', iconSize: [24, 24], iconAnchor: [12, 12], html: `<svg viewBox="0 0 24 24" width="24" height="24" style="transform:rotate(${res.plume.plumeDirDeg}deg)"><path d="M12 2l7 16-7-4-7 4z" fill="#bfe9ff"/></svg>` }),
  }).addTo(g)
}

// ---------------- 物资配送 ----------------
function drawSupply(res) {
  const g = layers.supply
  g.clearLayers()
  if (!res.supply) return
  const net = res.supply.network
  const sc = res.supply.schemes[state.supplyScheme]
  const catName = (c) => SUPPLY_CATEGORIES[c].name
  // 路线
  if (sc) {
    for (const p of sc.schedule) {
      for (const leg of p.legs) {
        if (leg.path.length < 2) continue
        const drone = leg.type === 'drone'
        L.polyline(llArr(leg.path), {
          pane: 'routes', color: drone ? '#c77dff' : SUPPLY_CATEGORIES[p.cat].color, weight: drone ? 2 : 2.2,
          opacity: drone ? 0.9 : 0.55, dashArray: drone ? '4 6' : '10 10', className: 'flow-line',
        }).bindTooltip(`<b>${esc(p.vehicle)}</b> ${drone ? '无人机' : '货车'} · ${catName(p.cat)} ${p.qty} 单位<br/>${esc(p.supply)}${p.relay ? ' → ' + esc(p.relay) : ''} → ${esc(p.demand)}<br/>送达 ${p.arrival.toFixed(1)} min（时间窗 ${p.deadline} min）`, { className: 'sim-tip', sticky: true }).addTo(g)
      }
    }
  }
  // 节点
  for (const s of net.supply) {
    const stock = Object.entries(s.stock).map(([c, q]) => `${catName(c)} ${q}`).join('、')
    L.marker(ll(s.lon, s.lat), { pane: 'nodes', icon: icon(s.kind === 'warehouse' ? 'warehouse' : 'fire') })
      .bindTooltip(`<b>${esc(s.name)}</b><br/>${s.kind === 'warehouse' ? '应急仓库（假设）' : '消防站'} · 供应点<br/><span style="color:#8fb3d9">库存：${stock}</span>`, { className: 'sim-tip', direction: 'top' }).addTo(g)
  }
  for (const r of net.relays) {
    L.marker(ll(r.lon, r.lat), { pane: 'nodes', icon: icon('relay') })
      .bindTooltip(`<b>${esc(r.name)}</b><br/>中转站 / 无人机起降点`, { className: 'sim-tip', direction: 'top' }).addTo(g)
  }
  const done = new Set(sc ? sc.schedule.map((p) => p.demandId + '|' + p.cat) : [])
  for (const d of net.demand) {
    const kind = d.group === 'rescue' ? 'rescue' : d.group === 'hospital' ? 'hospital' : 'shelterDemand'
    const items = Object.entries(d.demand).map(([c, q]) => `${done.has(d.id + '|' + c) ? '✔' : '✖'} ${catName(c)} ${q}`).join('<br/>')
    L.marker(ll(d.lon, d.lat), { pane: 'nodes', icon: icon(kind, d.group === 'hospital' ? 18 : 20) })
      .bindTooltip(`<b>${esc(d.name)}</b>${d.population ? `（就地避难 ${d.population.toLocaleString()} 人）` : ''}<br/>${items}`, { className: 'sim-tip', direction: 'top' }).addTo(g)
  }
}

// ---------------- 人员疏散 ----------------
function drawEvac(res) {
  const g = layers.evac
  g.clearLayers()
  originMarkers = []
  if (!res.evacuation) return
  const ev = res.evacuation
  const sc = ev.schemes[state.evacScheme]
  // 汇总 OD 流
  const flows = new Map()
  for (const x of sc.schedule) {
    const key = `${x.origin}|${x.dest}|${x.mode}`
    let f = flows.get(key)
    if (!f) { f = { ...x, total: 0, trips: 0 }; flows.set(key, f) }
    f.total += x.count
    f.trips++
  }
  for (const f of flows.values()) {
    const path = f.legs[1].path
    L.polyline(llArr(path), {
      pane: 'flows', color: VEHICLE_MODES[f.mode].color, weight: Math.min(7, 1.2 + Math.log10(1 + f.total) * 1.6),
      opacity: 0.6, dashArray: '8 8', className: 'flow-line',
    }).bindTooltip(`${esc(f.origin)} → ${esc(f.dest)}<br/>${VEHICLE_MODES[f.mode].name} ${f.trips} 车次 · ${f.total.toLocaleString()} 人`, { className: 'sim-tip', sticky: true }).addTo(g)
  }
  const dests = ev.destinations
  for (const h of dests.hospitals) L.marker(ll(h.lon, h.lat), { pane: 'nodes', icon: icon('hospital', 18) }).bindTooltip(`<b>${esc(h.name)}</b><br/>医院 · 接收容量 ${h.capacity}`, { className: 'sim-tip', direction: 'top' }).addTo(g)
  for (const s of dests.shelters) L.marker(ll(s.lon, s.lat), { pane: 'nodes', icon: icon('shelter', 18) }).bindTooltip(`<b>${esc(s.name)}</b><br/>避难所 · 容量 ${s.capacity}`, { className: 'sim-tip', direction: 'top' }).addTo(g)
  for (const s of dests.subways) L.marker(ll(s.lon, s.lat), { pane: 'nodes', icon: icon('subway', 18) }).bindTooltip(`<b>${esc(s.name)}</b><br/>地铁站${s.approx ? '（坐标近似）' : ''}`, { className: 'sim-tip', direction: 'top' }).addTo(g)
  // 起点
  const zc = { erpg3: '#ff4d4f', erpg2: '#ff8a3d', erpg1: '#ffd23f' }
  for (const o of ev.origins) {
    const tot = o.population[1] + o.population[2] + o.population[3]
    const m = L.circleMarker(ll(o.lon, o.lat), { pane: 'nodes', radius: 6 + Math.sqrt(tot) / 4, color: '#fff', weight: 1.5, fillColor: zc[o.zone], fillOpacity: 0.75 })
    m.bindTooltip('', { className: 'sim-tip', direction: 'top' })
    m.addTo(g)
    const lab = L.tooltip({ permanent: true, direction: 'center', className: 'map-label origin-label' }).setLatLng(ll(o.lon, o.lat)).setContent('').addTo(g)
    originMarkers.push({ o, m, lab, tot })
  }
  updateOrigins(state.playback.t)
}

function updateOrigins(t) {
  const res = result.value
  if (!res?.evacuation) return
  const sc = res.evacuation.schemes[state.evacScheme]
  const picked = new Map()
  for (const x of sc.schedule) if (x.pickup <= t) picked.set(x.origin, (picked.get(x.origin) || 0) + x.count)
  for (const { o, m, lab, tot } of originMarkers) {
    const rem = Math.max(0, tot - (picked.get(o.name) || 0))
    m.setRadius(4 + Math.sqrt(rem) / 4)
    m.setStyle({ fillOpacity: rem ? 0.75 : 0.2 })
    lab.setContent(rem ? rem.toLocaleString() : '✓')
    m.setTooltipContent(`<b>${esc(o.name)}</b> 疏散起点<br/>重伤 ${o.population[1]} · 脆弱 ${o.population[2]} · 一般 ${o.population[3]}<br/>T+${Math.round(t)} min 剩余 <b>${rem.toLocaleString()}</b> 人`)
  }
}

// ---------------- 车辆回放 ----------------
function prepPath(path) {
  const pts = llArr(path)
  const cum = [0]
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + pts[i - 1].distanceTo(pts[i]))
  return { pts, cum, len: cum[cum.length - 1] }
}
function along(pp, f) {
  if (pp.pts.length === 1 || pp.len === 0) return pp.pts[0]
  const d = f * pp.len
  let i = 1
  while (i < pp.cum.length - 1 && pp.cum[i] < d) i++
  const seg = pp.cum[i] - pp.cum[i - 1] || 1
  const u = (d - pp.cum[i - 1]) / seg
  const a = pp.pts[i - 1]
  const b = pp.pts[i]
  return L.latLng(a.lat + (b.lat - a.lat) * u, a.lng + (b.lng - a.lng) * u)
}

function buildVehicles(res) {
  layers.vehicles.clearLayers()
  const items = []
  const showSupply = state.view !== 'evac' && state.view !== 'hazard'
  const showEvac = state.view !== 'supply' && state.view !== 'hazard'
  if (showSupply && res.supply) {
    for (const p of res.supply.schemes[state.supplyScheme]?.schedule || []) {
      for (const leg of p.legs) {
        const drone = leg.type === 'drone'
        items.push({ t0: leg.t0, t1: leg.t1, pp: prepPath(leg.path), style: drone
          ? { radius: 4, color: '#fff', weight: 1, fillColor: '#c77dff', fillOpacity: 1 }
          : { radius: 4.5, color: '#fff', weight: 1, fillColor: SUPPLY_CATEGORIES[p.cat].color, fillOpacity: 1 } })
      }
    }
  }
  if (showEvac && res.evacuation) {
    for (const x of res.evacuation.schemes[state.evacScheme]?.schedule || []) {
      const c = VEHICLE_MODES[x.mode].color
      items.push({ t0: x.legs[0].t0, t1: x.legs[0].t1, pp: prepPath(x.legs[0].path), style: { radius: 3, color: c, weight: 1, fillColor: '#0a1a2f', fillOpacity: 0.9 } })
      items.push({ t0: x.legs[1].t0, t1: x.legs[1].t1, pp: prepPath(x.legs[1].path), style: { radius: x.mode === 'subway' || x.mode === 'bus' ? 5 : 3.6, color: '#fff', weight: 0.8, fillColor: c, fillOpacity: 1 } })
    }
  }
  for (const it of items) it.m = null
  vehicleState = items
  updateVehicles(state.playback.t)
}

function updateVehicles(t) {
  if (!vehicleState) return
  for (const it of vehicleState) {
    const active = t >= it.t0 && t <= it.t1 && it.t1 > it.t0
    if (active) {
      const pos = along(it.pp, (t - it.t0) / (it.t1 - it.t0))
      if (!it.m) it.m = L.circleMarker(pos, { ...it.style, renderer: layers.canvasVeh, interactive: false }).addTo(layers.vehicles)
      else it.m.setLatLng(pos)
    } else if (it.m) {
      layers.vehicles.removeLayer(it.m)
      it.m = null
    }
  }
}

// ---------------- 视图控制 ----------------
function applyView() {
  if (!map) return
  const v = state.view
  const show = (k, on) => (on ? map.hasLayer(layers[k]) || layers[k].addTo(map) : map.removeLayer(layers[k]))
  show('hazard', true)
  show('supply', v === 'overview' || v === 'supply')
  show('evac', v === 'overview' || v === 'evac')
  map.getPane('routes').style.opacity = v === 'overview' ? 0.4 : 1
  map.getPane('flows').style.opacity = v === 'overview' ? 0.7 : 1
  map.getPane('plume').style.opacity = v === 'hazard' ? 1 : 0.75
  map.getPane('zones').style.opacity = v === 'hazard' || v === 'evac' ? 1 : 0.7
}

function fitToView(animate = true) {
  const res = result.value
  if (!res || !map) return
  const pts = []
  const add = (lon, lat) => pts.push(ll(lon, lat))
  const inc = res.params.incident
  add(inc.lon, inc.lat)
  const z = res.zones.polygons
  const zb = geo(z.erpg1).getBounds()
  if (zb.isValid()) { pts.push(zb.getSouthWest(), zb.getNorthEast()) }
  if ((state.view === 'overview' || state.view === 'supply') && res.supply) {
    res.supply.network.supply.forEach((s) => { if (!s.name.startsWith('假设仓库')) add(s.lon, s.lat) })
    res.supply.network.demand.forEach((s) => add(s.lon, s.lat))
  }
  if ((state.view === 'overview' || state.view === 'evac') && res.evacuation) {
    res.evacuation.origins.forEach((o) => add(o.lon, o.lat))
    const d = res.evacuation.destinations
    ;[...d.hospitals, ...d.shelters].forEach((s) => add(s.lon, s.lat))
  }
  const b = L.latLngBounds(pts)
  map.fitBounds(b, { ...panelPadding(), animate, maxZoom: 15 })
}

function rebuild() {
  const res = result.value
  if (!res || !map) return
  drawIncident()
  drawHazard(res)
  drawSupply(res)
  drawEvac(res)
  buildVehicles(res)
  applyView()
  if (!fitDone || state.runCount <= 1) { fitToView(false); fitDone = true } else fitToView(true)
}

watch(result, rebuild)
watch(() => staticData.value, drawBoundary)
watch(() => [state.params.incident.lon, state.params.incident.lat], () => {
  drawIncident()
  if (state.params.siteId === 'custom') map?.panTo(ll(state.params.incident.lon, state.params.incident.lat))
})
watch(() => state.view, () => { applyView(); if (result.value) { buildVehicles(result.value); fitToView(true) } })
watch(() => state.supplyScheme, () => { if (result.value) { drawSupply(result.value); buildVehicles(result.value) } })
watch(() => state.evacScheme, () => { if (result.value) { drawEvac(result.value); buildVehicles(result.value) } })
watch(() => state.playback.t, (t) => { updateVehicles(t); updateOrigins(t) })
watch(() => [state.leftCollapsed, state.rightCollapsed], () => setTimeout(() => fitToView(true), 380))
</script>

<style>
.map { position: absolute; inset: 0; }
.fac-ico, .inc-ico, .wind-arrow { background: none; border: none; }
.fac-ico svg { filter: drop-shadow(0 0 3px rgba(0, 0, 0, 0.8)); }
.inc-wrap { position: relative; width: 32px; height: 44px; }
.inc-wrap svg { position: relative; filter: drop-shadow(0 0 6px rgba(255, 60, 60, 0.9)); }
.inc-wrap .pulse {
  position: absolute; left: 16px; top: 42px; width: 12px; height: 12px; margin: -6px 0 0 -6px;
  border-radius: 50%; border: 2px solid #ff4d4f; animation: inc-pulse 2s ease-out infinite;
}
.inc-wrap .pulse.p2 { animation-delay: 1s; }
@keyframes inc-pulse { from { transform: scale(1); opacity: 1; } to { transform: scale(7); opacity: 0; } }
.flow-line { animation: flow-dash 1.4s linear infinite; }
@keyframes flow-dash { to { stroke-dashoffset: -36; } }
.plume-img { image-rendering: auto; }
.zone-label { font-size: 13px !important; font-weight: 700; }
.origin-label { font-size: 11px !important; font-weight: 700; color: #fff !important; }
</style>
