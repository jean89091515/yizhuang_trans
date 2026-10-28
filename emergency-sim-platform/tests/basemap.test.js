import { test } from 'node:test'
import assert from 'node:assert/strict'
import { decodeBasemap, roadStatus, labelCandidates } from '../src/utils/basemap.js'

// 与 tools/export_platform_data.py encode_line 相同的编码：×1e5 取整差分
const enc = (cs) => cs.flatMap(([x, y], i) => (i ? [Math.round(x * 1e5) - Math.round(cs[i - 1][0] * 1e5), Math.round(y * 1e5) - Math.round(cs[i - 1][1] * 1e5)] : [Math.round(x * 1e5), Math.round(y * 1e5)]))

const LON = 116.494
const LAT = 39.7356
const KX = 111320 * Math.cos((LAT * Math.PI) / 180)
// 一条穿过事故点、东西向 10 km 的主干路
const line = [[LON - 5000 / KX, LAT], [LON + 5000 / KX, LAT]]
const raw = {
  names: ['测试大街'],
  roads: [[4, 0, enc(line)], [10, -1, enc([[LON, LAT + 0.1], [LON + 0.01, LAT + 0.1]])]],
  subway: [{ name: '亦庄线', color: '#E91E63', d: enc(line) }],
  subway_stations: [],
}

test('basemap.json 解码与长度', () => {
  const bm = decodeBasemap(raw)
  assert.equal(bm.roads.length, 2)
  assert.equal(bm.roads[0].name, '测试大街')
  assert.equal(bm.roads[1].name, null)
  assert.ok(Math.abs(bm.roads[0].coords[1][0] - line[1][0]) < 1e-5)
  assert.ok(Math.abs(bm.roads[0].lenM - 10000) < 15, `长度 ${bm.roads[0].lenM}`)
  assert.equal(bm.subway[0].coords.length, 2)
})

test('路网状态按封闭/拥堵圈裁剪（与引擎 BPR 系数一致）', () => {
  const bm = decodeBasemap(raw)
  const res = { params: { incident: { lon: LON, lat: LAT }, roads: { bprAlpha: 0.15, bprBeta: 4, vc: 0.8 } }, roads: { closureRadiusM: 1000, congestionRadiusM: 3000 } }
  const st = roadStatus(bm, res)
  const km = (lv) => st.filter((x) => x.level === lv).reduce((s, x) => s + x.lenM, 0)
  // 远处道路不着色；穿过事故点的道路：封闭 2 km，拥堵合计 4 km（只算 3 km 圈内）
  assert.ok(st.every((x) => x.road === bm.roads[0]))
  assert.ok(Math.abs(km('closed') - 2000) < 100, `封闭 ${km('closed')}`)
  const congested = km('heavy') + km('medium') + km('light')
  assert.ok(Math.abs(congested - 4000) < 120, `拥堵 ${congested}`)
  // f = 1.0614·(1 + (3000 − r)/3000)，≥1.5 的严重拥堵约在 r < 1761 m
  assert.ok(Math.abs(km('heavy') - 2 * 761) < 120, `严重拥堵 ${km('heavy')}`)
  for (const x of st.filter((y) => y.level !== 'closed')) assert.ok(x.fmin >= 1.06 && x.fmax <= 1.77)
})

test('道路名称标注候选取路段中点', () => {
  const c = labelCandidates(decodeBasemap(raw))
  assert.equal(c.length, 1)
  assert.equal(c[0].name, '测试大街')
  assert.ok(Math.abs(c[0].mid[0] - LON) < 1e-4)
})
