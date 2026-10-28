#!/usr/bin/env node
/**
 * 打包交付给部署同事的发布包：release/emergency-sim-<日期>.tar.gz
 *
 *   npm run build && npm run package
 *
 * 包含：dist/（前端 + data，直接部署即可）、server/ + src/engine/ + package*.json（可选服务端求解）、
 *       deploy/、examples/、docs/、README.md。不含 node_modules 与源码中的其他部分。
 * 注意：dist/data 中是构建时 public/data 的数据（导出真实数据后即为真实数据），请按数据授权要求传递。
 */
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const must = ['dist/index.html', 'dist/config.js', 'dist/data/facilities.json', 'dist/data/population.json']
for (const f of must) {
  if (!fs.existsSync(path.join(ROOT, f))) {
    console.error(`缺少 ${f}，请先运行 npm run build`)
    process.exit(1)
  }
}
const pop = JSON.parse(fs.readFileSync(path.join(ROOT, 'dist/data/population.json'), 'utf-8'))
const hasRoads = fs.existsSync(path.join(ROOT, 'dist/data/road_network.json'))
const d = new Date()
const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}-${String(d.getHours()).padStart(2, '0')}${String(d.getMinutes()).padStart(2, '0')}`
fs.mkdirSync(path.join(ROOT, 'release'), { recursive: true })
const out = path.join('release', `emergency-sim-${stamp}.tar.gz`)
const items = ['dist', 'server', 'src/engine', 'package.json', 'package-lock.json', 'deploy', 'examples', 'docs', 'README.md']
  .filter((p) => fs.existsSync(path.join(ROOT, p)))
execFileSync('tar', ['-czf', out, ...items], { cwd: ROOT, stdio: 'inherit' })
const mb = (fs.statSync(path.join(ROOT, out)).size / 1e6).toFixed(1)
console.log(`已生成 ${out}（${mb} MB）`)
console.log(`  数据：${pop.meta?.approximate ? '默认近似数据' : '真实数据（来自导出脚本）'}${hasRoads ? '，含路网' : '，无路网（几何近似行程时间）'}`)
console.log('  部署步骤见 docs/部署指南.md')
