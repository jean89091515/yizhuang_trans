import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { runSimulation, paramsFromPresets, wgs84ToGcj02, gcj02ToWgs84, DEFAULT_PARAMS } from '../src/engine/index.js'
import { concentration, computePlume } from '../src/engine/plume.js'
import { distanceTransform, loadPopulation } from '../src/engine/zones.js'
import { RoadGraph, TravelModel } from '../src/engine/travel.js'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
// 测试固定使用默认数据副本（public/data 可能已被导出脚本替换为真实数据）
const rd = (f) => JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'default-data', f), 'utf-8'))
const data = { facilities: rd('facilities.json'), population: rd('population.json') }
const ref = rd('paper_reference.json')

let baseRes
const base = async () => (baseRes ??= await runSimulation(paramsFromPresets({ siteId: 'taihe', windPresetId: 'sw2' }), data))

test('高斯烟羽与 Step9 plume_concentration.npz 一致', () => {
  const Q = (5 * 1e6) / 60
  // npz 东北对角线采样值（50 m 网格，k 格 → k·50·√2 m）
  const cases = [[3, 26.45773029142524], [10, 3.263063392278462], [20, 1.1100552020471337], [30, 0.6206265495264376]]
  for (const [k, expected] of cases) {
    const c = concentration(k * 50 * Math.SQRT2, 0, Q, 3.0, 2.0, 'D')
    assert.ok(Math.abs(c - expected) / expected < 1e-6, `k=${k}: ${c} vs ${expected}`)
  }
  const p = computePlume({ ...DEFAULT_PARAMS })
  assert.ok(Math.abs(p.max - 199.9952463412597) < 1e-3)
})

test('欧氏距离变换', () => {
  const n = 7
  const m = new Uint8Array(n * n)
  m[3 * n + 3] = 1
  const d = distanceTransform(m, n)
  assert.equal(d[3 * n + 3], 0)
  assert.ok(Math.abs(d[0] - Math.hypot(3, 3)) < 1e-9)
  assert.ok(Math.abs(d[3 * n + 6] - 3) < 1e-9)
})

test('基准场景 ERPG 分区人口与论文偏差 < 5%', async () => {
  const r = await base()
  const zp = r.zones.populations
  assert.ok(Math.abs(zp.erpg2.total - ref.erpg_zone_populations.erpg2) / ref.erpg_zone_populations.erpg2 < 0.05)
  assert.ok(Math.abs(zp.erpg1.total - ref.erpg_zone_populations.erpg1) / ref.erpg_zone_populations.erpg1 < 0.05)
  // 论文：需疏散 13,830 人（ERPG-2 k1+k2，ERPG-1 k1）
  assert.ok(Math.abs(r.zones.evacDemand - 13830) / 13830 < 0.05, `evacDemand=${r.zones.evacDemand}`)
})

test('基准疏散：完成率接近论文 41.0%，k=2 全部疏散', async () => {
  const r = await base()
  const all = r.evacuation.schemes.all
  assert.ok(Math.abs(all.rate - 0.41) < 0.03, `rate=${all.rate}`)
  assert.equal(all.byClass[2].rate, 1)
  assert.ok(all.byClass[1].rate < 0.15, 'k=1 受救护车/直升机运力约束')
  // 双倍救护车 → 疏散更多、风险更低
  assert.ok(r.evacuation.schemes.double_amb.evacuated > all.evacuated)
  assert.ok(r.evacuation.schemes.double_amb.totalRisk <= all.totalRisk)
  // 救护车敏感性单调
  const s = r.evacuation.sensitivityAmbulance
  for (let i = 1; i < s.length; i++) assert.ok(s[i].k1Rate >= s[i - 1].k1Rate)
})

test('基准物资配送：网络规模与论文一致，生命救援 100% 准时', async () => {
  const r = await base()
  assert.equal(r.supply.network.supply.length, 10)
  assert.equal(r.supply.network.relays.length, 6)
  assert.equal(r.supply.network.demand.length, 25)
  assert.ok(r.supply.taskCount >= 66 && r.supply.taskCount <= 70)
  for (const k of ['truck_only', 'coordinated']) {
    const sc = r.supply.schemes[k]
    assert.equal(sc.lifeOnTimeRate, 1)
    assert.ok(sc.completionRate > 0.85)
  }
  assert.equal(r.supply.schemes.truck_only.routes.relay, 0)
  assert.ok(r.supply.schemes.coordinated.routes.relay > 0)
  // 纯无人机：绝大部分任务超出 25 kg 载重
  assert.ok(r.supply.schemes.drone_only.completed <= 2)
})

test('韧性：路网连通性 = 1 − 96.7/505.3', async () => {
  const r = await base()
  assert.ok(Math.abs(r.resilience.structural.connectivity - (1 - 96.73 / 505.28)) < 1e-3)
  assert.equal(r.resilience.radar.length, 5)
})

test('七级大风：无人机停飞，无接力任务', async () => {
  const r = await runSimulation(paramsFromPresets({ siteId: 'taihe', windPresetId: 'sw7' }), data)
  assert.equal(r.scenario.dronesGrounded, true)
  assert.equal(r.supply.schemes.coordinated.routes.relay, 0)
  assert.equal(r.supply.schemes.coordinated.routes.drone, 0)
})

test('风向改变 → 烟羽去向改变，结果确定可复现', async () => {
  const p = paramsFromPresets({ siteId: 'taihe', windPresetId: 'n2' })
  const a = await runSimulation(p, data)
  const b = await runSimulation(p, data)
  assert.equal(a.plume.plumeDirDeg, 180)
  assert.equal(a.evacuation.schemes.all.evacuated, b.evacuation.schemes.all.evacuated)
  assert.equal(a.supply.schemes.coordinated.makespan, b.supply.schemes.coordinated.makespan)
})

test('仅疏散 / 仅物资 方法', async () => {
  const e = await runSimulation({ ...paramsFromPresets({}), method: 'evac' }, data)
  assert.ok(e.evacuation && !e.supply)
  const s = await runSimulation({ ...paramsFromPresets({}), method: 'supply' }, data)
  assert.ok(s.supply && !s.evacuation)
  assert.equal(s.supply.taskCount, 40) // 不含就地避难需求（同 Step10 未读取 Step11 输出时）
})

test('WGS84 ↔ GCJ-02 往返误差 < 1e-6°', () => {
  const [gx, gy] = wgs84ToGcj02(116.494, 39.7356)
  assert.ok(Math.abs(gx - 116.494) > 1e-4) // 有偏移
  const [x, y] = gcj02ToWgs84(gx, gy)
  assert.ok(Math.abs(x - 116.494) < 1e-6 && Math.abs(y - 39.7356) < 1e-6)
})

test('可选路网：Dijkstra 行程时间与封闭', () => {
  // 5×5 网格路网，间距 0.01°，以中心为事故点
  const nodes = []
  const edges = []
  const id = (i, j) => i * 5 + j
  for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) nodes.push(116.47 + j * 0.01, 39.71 + i * 0.01)
  const len = 0.01 * 111320 * Math.cos((39.73 * Math.PI) / 180)
  for (let i = 0; i < 5; i++) {
    for (let j = 0; j < 5; j++) {
      if (j < 4) edges.push(id(i, j), id(i, j + 1), len, 60, id(i, j + 1), id(i, j), len, 60)
      if (i < 4) edges.push(id(i, j), id(i + 1, j), 1105.4, 60, id(i + 1, j), id(i, j), 1105.4, 60)
    }
  }
  const g = new RoadGraph({ nodes, edges })
  const roads = { ...DEFAULT_PARAMS.roads, closureRadiusM: 500, congestionRadiusM: 600 }
  const tm = new TravelModel({ incident: { lon: 116.49, lat: 39.73 }, roads, graph: g })
  // 沿最南一行从西到东 4 段，远离事故点（无拥堵），60 km/h
  const t = tm.time({ lon: 116.47, lat: 39.71 }, { lon: 116.51, lat: 39.71 }, 60, 'ground')
  assert.ok(Math.abs(t - (4 * len) / 1000) < 1e-6, `t=${t}`)
  // 穿越中心的东西向路段被封闭 → 需绕行，耗时更长
  const t2 = tm.time({ lon: 116.47, lat: 39.73 }, { lon: 116.51, lat: 39.73 }, 60, 'ground')
  assert.ok(t2 > (4 * len) / 1000)
})

test('逐地块年龄结构：优先于全局比例', async () => {
  const pop = structuredClone(data.population)
  const n = pop.blocks.length
  pop.block_age = { children: Array(n).fill(0.05), elderly: Array(n).fill(0.05) }
  const d2 = { facilities: data.facilities, population: pop }
  const r = await runSimulation(paramsFromPresets({}), d2)
  const o = r.evacuation.origins.find((x) => x.zone === 'erpg2')
  // ERPG-2 疏散 k=1、k=2：k=2 应按 10% 计，而不是全局 27%
  assert.ok(Math.abs(o.population[2] / o.sectorPop - 0.10) < 0.01, `k2=${o.population[2] / o.sectorPop}`)
  const z = r.zones.populations.erpg2
  assert.ok(Math.abs((z.children + z.elderly) / z.total - 0.10) < 0.01)
  assert.equal(loadPopulation(data.population).blockAge, null)
})

test('路网长度统计：双向道路只计一次', () => {
  // 两节点间一条双向路（1000 m）+ 一条单向路（500 m）
  const g = new RoadGraph({ nodes: [116.49, 39.73, 116.5017, 39.73, 116.49, 39.7345], edges: [0, 1, 1000, 40, 1, 0, 1000, 40, 0, 2, 500, 40] })
  const [km] = g.lengthWithin({ toXY: () => [0, 0] }, [10])
  assert.ok(Math.abs(km - 1.5) < 1e-9, `km=${km}`)
})
