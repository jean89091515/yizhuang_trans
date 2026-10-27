#!/usr/bin/env node
/**
 * 命令行运行模拟引擎（不依赖浏览器），输出关键指标并与论文基准对照。
 *
 *   node tools/run_cli.js                      # 太和桥 + 二级西南风（论文基准）
 *   node tools/run_cli.js --wind n2            # 换风况预设
 *   node tools/run_cli.js --json out.json      # 保存完整结果
 *   node tools/run_cli.js --params p.json      # 自定义参数（与 DEFAULT_PARAMS 深合并）
 *   node tools/run_cli.js --data other/data    # 使用其他数据目录（如导出脚本输出）
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { runSimulation, paramsFromPresets, mergeParams } from '../src/engine/index.js'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const args = process.argv.slice(2)
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d }

export function loadData(dir = path.join(ROOT, 'public', 'data')) {
  const rd = (f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf-8'))
  const data = { facilities: rd('facilities.json'), population: rd('population.json') }
  if (fs.existsSync(path.join(dir, 'road_network.json'))) data.roadNetwork = rd('road_network.json')
  return data
}

async function main() {
  const data = loadData(arg('--data') ? path.resolve(arg('--data')) : undefined)
  let params = paramsFromPresets({ siteId: arg('--site', 'taihe'), windPresetId: arg('--wind', 'sw2') })
  if (arg('--params')) params = mergeParams(params, JSON.parse(fs.readFileSync(arg('--params'), 'utf-8')))
  if (arg('--algorithm')) params.algorithm = arg('--algorithm')
  const res = await runSimulation(params, data, { onLog: (e) => console.log(`[${e.t.toFixed(3)}s] ${e.msg}`) })
  const ref = JSON.parse(fs.readFileSync(path.join(ROOT, 'public', 'data', 'paper_reference.json'), 'utf-8'))
  console.log('\n===== 与论文基准对照（仅基准场景有意义） =====')
  const zp = res.zones.populations
  console.log(`ERPG-2 人口  平台 ${zp.erpg2.total}  论文 ${ref.erpg_zone_populations.erpg2}`)
  console.log(`ERPG-1 人口  平台 ${zp.erpg1.total}  论文 ${ref.erpg_zone_populations.erpg1}`)
  if (res.evacuation) {
    for (const [k, rk] of [['all', 'baseline'], ['no_subway', 'no_subway'], ['no_heli', 'no_helicopter'], ['strict', 'strict_priority']]) {
      const a = res.evacuation.schemes[k]; const b = ref.evacuation[rk]
      console.log(`疏散 ${a.label.padEnd(6)} 平台 ${a.evacuated}/${a.total} ${(a.rate * 100).toFixed(1)}% 风险 ${Math.round(a.totalRisk)} | 论文 ${b.evacuated}/${b.evacuated + b.remaining} ${(b.evac_rate * 100).toFixed(1)}% 风险 ${Math.round(b.total_risk)}`)
    }
  }
  if (res.supply) {
    for (const [k, rk] of [['truck_only', 'truck_only'], ['coordinated', 'coordinated'], ['coord_double', 'coord_more_drones'], ['drone_only', 'drone_only']]) {
      const a = res.supply.schemes[k]; const b = ref.supply[rk]
      console.log(`配送 ${a.label.padEnd(12)} 平台 ${a.completed}/${a.totalTasks} mk ${a.makespan.toFixed(1)} 直/接 ${a.routes.direct}/${a.routes.relay} | 论文 ${b.completed_tasks}/${b.total_tasks} mk ${b.makespan_min.toFixed(1)} 直/接 ${b.route_types.direct}/${b.route_types.relay}`)
    }
  }
  console.log('韧性雷达', res.resilience.radar.map((r) => `${r.name}=${r.value === null ? '—' : (r.value * 100).toFixed(1) + '%'}`).join('  '))
  if (arg('--json')) { fs.writeFileSync(arg('--json'), JSON.stringify(res)); console.log('saved', arg('--json')) }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main()
