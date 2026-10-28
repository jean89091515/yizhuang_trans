#!/usr/bin/env node
/**
 * 路网与疏散诊断：用于排查真实数据下各方案结果差异（如“无地铁”疏散率）。
 *
 *   node tools/diagnose.js                 # 基准场景（太和桥 · 二级西南风）
 *   node tools/diagnose.js --data dir      # 指定数据目录
 *
 * 输出：路网连通性（封闭前后）、起点/目的地吸附到路网的距离、路网行程时间与几何近似的比值、
 * 不可达（回退几何模型）比例、各方案各交通方式的车次/人数/行程/周转时间。
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { runSimulation, paramsFromPresets, prepareData, VEHICLE_MODES } from '../src/engine/index.js'
import { TravelModel } from '../src/engine/travel.js'
import { buildDestinations } from '../src/engine/evacuation.js'
import { distM } from '../src/engine/geo.js'
import { loadData } from './run_cli.js'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const args = process.argv.slice(2)
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d }
const f1 = (v) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : v.toFixed(1))
const pct = (v) => (Number.isFinite(v) ? (v * 100).toFixed(1) + '%' : '—')
const median = (a) => { if (!a.length) return NaN; const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)] }

async function main() {
  const data = loadData(arg('--data') ? path.resolve(arg('--data')) : undefined)
  prepareData(data)
  const params = paramsFromPresets({ siteId: 'taihe', windPresetId: 'sw2' })
  const res = await runSimulation(params, data)
  const g = data._graph
  const inc = params.incident
  console.log(`数据目录 ${arg('--data') || path.join(ROOT, 'public', 'data')}`)
  console.log(`行程时间模型：${res.roads.travelModel}${g ? `（节点 ${g.N}，有向边 ${g.to.length}）` : ''}`)

  // ---------- 路网连通性 ----------
  let inLargest = () => true
  if (g) {
    const tm = new TravelModel({ incident: inc, roads: params.roads, graph: g })
    const closed = g.factor.reduce((s, f) => s + (f === Infinity ? 1 : 0), 0)
    const mc = g.mainComponent()
    inLargest = (node) => mc.inMain[node] === 1
    console.log(`\n[路网] 封闭删除有向边 ${closed}（${pct(closed / g.to.length)}）；封闭后最大强连通分量 ${mc.size} 节点（${pct(mc.size / g.N)}），分量数 ${mc.count}`)

    const nodesInfo = (label, list) => {
      const rows = list.map((p) => {
        const n = g.nearest(p.lon, p.lat)
        const d = distM(p, { lon: g.lon[n], lat: g.lat[n] })
        return { name: p.name, snap: d, scc: inLargest(n), dInc: distM(p, inc) }
      })
      const bad = rows.filter((r) => !r.scc)
      console.log(`  ${label} ${rows.length} 个：吸附距离 中位 ${f1(median(rows.map((r) => r.snap)))} m，最大 ${f1(Math.max(...rows.map((r) => r.snap)))} m；不在最大强连通分量 ${bad.length} 个` +
        (bad.length ? `（${bad.slice(0, 6).map((r) => `${r.name}@${Math.round(r.dInc)}m`).join('、')}）` : ''))
      return rows
    }
    const ev = res.evacuation
    console.log('[吸附] 点位 → 最近路网节点')
    nodesInfo('疏散起点', ev.origins)
    nodesInfo('医院', ev.destinations.hospitals)
    nodesInfo('避难所', ev.destinations.shelters)
    nodesInfo('供应点', res.supply.network.supply.filter((s) => s.kind !== 'warehouse'))
    nodesInfo('配送需求点', res.supply.network.demand)

    // ---------- 起点 → 目的地：路网 vs 几何 ----------
    console.log('\n[行程时间] 疏散起点 → 医院/避难所（公交 30 km/h）：路网时间 / 几何近似')
    const dests = [...ev.destinations.hospitals, ...ev.destinations.shelters]
    for (const o of ev.origins) {
      const ratios = []
      let unreachable = 0
      let best = Infinity
      let bestGeo = Infinity
      for (const d of dests) {
        const tn = g.timeMin(o, d, 30)
        const [ax, ay] = tm.local.toXY(o.lon, o.lat)
        const [bx, by] = tm.local.toXY(d.lon, d.lat)
        const tg = tm.geometricTime(ax, ay, bx, by, 30)
        if (tn === null) unreachable++
        else { ratios.push(tn / tg); best = Math.min(best, tn) }
        bestGeo = Math.min(bestGeo, tg)
      }
      const pop = o.population[1] + o.population[2] + o.population[3]
      console.log(`  ${o.name.padEnd(9)} 距事故点 ${String(Math.round(distM(o, inc))).padStart(5)} m，需疏散 ${String(pop).padStart(5)}：` +
        `最近目的地 路网 ${f1(best)} / 几何 ${f1(bestGeo)} min，比值中位 ${f1(median(ratios))}，不可达 ${unreachable}/${dests.length}`)
    }
  }

  // ---------- 各方案各方式 ----------
  console.log('\n[方案] 各交通方式：车次 / 人数 / 平均载客行程 / 平均周转（出发→送达→返回）')
  for (const key of ['all', 'no_subway', 'no_heli']) {
    const sc = res.evacuation.schemes[key]
    console.log(`  「${sc.label}」疏散 ${sc.evacuated}/${sc.total}（${pct(sc.rate)}）；k=1 ${pct(sc.byClass[1].rate)}，k=2 ${pct(sc.byClass[2].rate)}`)
    for (const m of Object.keys(VEHICLE_MODES)) {
      const xs = sc.schedule.filter((x) => x.mode === m)
      if (!xs.length) continue
      const cyc = xs.map((x) => x.arrival - x.t + x.travelMin + params.evacuation.unloadMin)
      console.log(`    ${VEHICLE_MODES[m].name.padEnd(4)} 车次 ${String(xs.length).padStart(3)}，人数 ${String(xs.reduce((s, x) => s + x.count, 0)).padStart(5)}，` +
        `载客行程 ${f1(xs.reduce((s, x) => s + x.travelMin, 0) / xs.length)} min，周转 ${f1(cyc.reduce((a, b) => a + b, 0) / cyc.length)} min，最晚送达 ${f1(Math.max(...xs.map((x) => x.arrival)))} min`)
    }
  }

  // ---------- 路网口径对比 ----------
  if (g) {
    const variant = (roads) => runSimulation({ ...params, roads: { ...params.roads, ...roads } }, data)
    const runs = [
      ['A 当前默认（最近节点，车速上限）', res],
      ['B 吸附主连通路网+接入段', await variant({ snapToMainComponent: true })],
      ['C 论文路由口径（不限车速）', await variant({ vehicleSpeedCap: false })],
      ['D = B + C', await variant({ snapToMainComponent: true, vehicleSpeedCap: false })],
    ]
    console.log('\n[对比] 路网口径（疏散率 / 累计风险万 ；配送完成 / Makespan）')
    console.log('  ' + ['方案'.padEnd(10), ...runs.map(([n]) => n.slice(0, 1))].join('   '))
    for (const key of ['all', 'double_amb', 'no_subway', 'no_heli', 'strict']) {
      const cells = runs.map(([, r]) => `${pct(r.evacuation.schemes[key].rate)}/${(r.evacuation.schemes[key].totalRisk / 1e4).toFixed(0)}`)
      console.log(`  疏散 ${res.evacuation.schemes[key].label.padEnd(6)} ${cells.join('   ')}`)
    }
    for (const key of ['truck_only', 'coordinated']) {
      const cells = runs.map(([, r]) => `${r.supply.schemes[key].completed}/${r.supply.schemes[key].totalTasks} ${f1(r.supply.schemes[key].makespan)}`)
      console.log(`  配送 ${res.supply.schemes[key].label.slice(0, 6).padEnd(6)} ${cells.join('   ')}`)
    }
    for (const [n, r] of runs) {
      const bus = r.evacuation.schemes.no_subway.schedule.filter((x) => x.mode === 'bus')
      const cyc = bus.map((x) => x.arrival - x.t + x.travelMin + params.evacuation.unloadMin)
      console.log(`  ${n}：无地铁方案公交 ${bus.length} 车次，平均周转 ${f1(cyc.reduce((a, b) => a + b, 0) / (cyc.length || 1))} min`)
    }
    console.log('  论文：无地铁 38.8%（公交 84 车次运 4,009 人）；全部资源 41.0%')
  }
}

main()
