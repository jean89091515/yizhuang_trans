#!/usr/bin/env node
/**
 * 服务端求解器（可选）—— 与前端共用同一计算引擎（src/engine），零第三方 Web 框架依赖。
 *
 *   PORT=8787 DATA_DIR=./public/data STATIC_DIR=./dist node server/index.js
 *
 * 接口：
 *   GET  /api/emergency/health                 健康检查
 *   GET  /api/emergency/config                 默认参数、站点/风况预设、方案列表、计算阶段
 *   GET  /api/emergency/reference              论文基准结果
 *   POST /api/emergency/simulate               body: { params }，返回完整结果 JSON
 *   POST /api/emergency/simulate?stream=1      NDJSON 流：{type:'stage'|'log'|'result'|'error', ...}
 *   POST /api/emergency/simulate?summary=1     仅返回摘要（不含调度明细与几何）
 * 其他 GET 请求：若配置了 STATIC_DIR，则作为静态文件服务（单服务部署前端 + 接口）。
 */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  runSimulation, prepareData, paramsFromPresets, mergeParams, DEFAULT_PARAMS, SITES, WIND_PRESETS, STAGES, EVAC_SCHEMES, SUPPLY_SCHEMES, ENGINE_VERSION,
} from '../src/engine/index.js'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const PORT = +(process.env.PORT || 8787)
// 数据目录：DATA_DIR > public/data > dist/data（发布包中只有 dist/data）
const DATA_DIR = path.resolve(process.env.DATA_DIR ||
  [path.join(ROOT, 'public', 'data'), path.join(ROOT, 'dist', 'data')].find((d) => fs.existsSync(path.join(d, 'facilities.json'))) ||
  path.join(ROOT, 'public', 'data'))
const STATIC_DIR = process.env.STATIC_DIR ? path.resolve(process.env.STATIC_DIR) : (fs.existsSync(path.join(ROOT, 'dist')) ? path.join(ROOT, 'dist') : null)
const CORS = process.env.CORS_ORIGIN || '*'
const MAX_BODY = 1 << 20

const readJson = (f) => JSON.parse(fs.readFileSync(path.join(DATA_DIR, f), 'utf-8'))
const data = { facilities: readJson('facilities.json'), population: readJson('population.json') }
if (fs.existsSync(path.join(DATA_DIR, 'road_network.json'))) data.roadNetwork = readJson('road_network.json')
prepareData(data)
const reference = fs.existsSync(path.join(DATA_DIR, 'paper_reference.json')) ? readJson('paper_reference.json') : null

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.geojson': 'application/geo+json; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.woff2': 'font/woff2' }

function send(res, code, body, type = 'application/json; charset=utf-8') {
  res.writeHead(code, { 'Content-Type': type, 'Access-Control-Allow-Origin': CORS, 'Access-Control-Allow-Headers': 'Content-Type' })
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body))
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0
    const chunks = []
    req.on('data', (c) => {
      size += c.length
      if (size > MAX_BODY) { reject(new Error('请求体过大')); req.destroy() } else chunks.push(c)
    })
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')))
    req.on('error', reject)
  })
}

function summary(r) {
  const strip = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => {
    const { schedule, timeline, ...rest } = v
    return [k, rest]
  }))
  return {
    version: r.version, params: r.params, scenario: r.scenario, elapsedMs: r.elapsedMs, computeMs: r.computeMs,
    plume: { maxConc: r.plume.maxConc, reach: r.plume.reach, plumeDirDeg: r.plume.plumeDirDeg },
    zones: { populations: r.zones.populations, circles: r.zones.circles, evacDemand: r.zones.evacDemand, shelterInPlace: r.zones.shelterInPlace },
    roads: r.roads,
    evacuation: r.evacuation && { schemes: strip(r.evacuation.schemes), sensitivityAmbulance: r.evacuation.sensitivityAmbulance },
    supply: r.supply && { schemes: strip(r.supply.schemes), sensitivityDrones: r.supply.sensitivityDrones, taskCount: r.supply.taskCount },
    resilience: r.resilience,
  }
}

async function handleSimulate(req, res, url) {
  let body = {}
  try {
    const raw = await readBody(req)
    body = raw ? JSON.parse(raw) : {}
  } catch (e) {
    return send(res, 400, { error: `请求解析失败：${e.message}` })
  }
  // 先按 siteId / windPresetId 展开预设，再与显式参数深合并
  const raw = body.params || body
  const base = paramsFromPresets({ siteId: raw.siteId, windPresetId: raw.windPresetId, incident: raw.incident })
  const params = { ...mergeParams(base, raw), solver: 'local', stageDelayMs: 0 }
  if (url.searchParams.get('stream') === '1') {
    res.writeHead(200, { 'Content-Type': 'application/x-ndjson; charset=utf-8', 'Access-Control-Allow-Origin': CORS, 'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no' })
    const w = (o) => res.write(JSON.stringify(o) + '\n')
    try {
      const r = await runSimulation(params, data, { onStage: (p) => w({ type: 'stage', payload: p }), onLog: (p) => w({ type: 'log', payload: p }) })
      w({ type: 'result', result: r })
    } catch (e) {
      w({ type: 'error', message: e.message })
    }
    return res.end()
  }
  try {
    const r = await runSimulation(params, data)
    send(res, 200, url.searchParams.get('summary') === '1' ? summary(r) : r)
  } catch (e) {
    send(res, 500, { error: e.message })
  }
}

function serveStatic(res, pathname) {
  if (!STATIC_DIR) return send(res, 404, { error: 'not found' })
  let p = path.normalize(decodeURIComponent(pathname)).replace(/^([/\\])+/, '')
  if (!p || p.endsWith('/') || p.endsWith('\\')) p = path.join(p, 'index.html')
  const file = path.join(STATIC_DIR, p)
  if (!file.startsWith(STATIC_DIR)) return send(res, 403, { error: 'forbidden' })
  fs.readFile(file, (err, buf) => {
    if (err) return send(res, 404, { error: 'not found' })
    send(res, 200, buf, MIME[path.extname(file)] || 'application/octet-stream')
  })
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  if (req.method === 'OPTIONS') return send(res, 204, '')
  const p = url.pathname.replace(/\/+$/, '')
  try {
    if (req.method === 'GET' && p === '/api/emergency/health') return send(res, 200, { ok: true, version: ENGINE_VERSION, roadNetwork: !!data.roadNetwork })
    if (req.method === 'GET' && p === '/api/emergency/config') {
      return send(res, 200, { defaults: DEFAULT_PARAMS, sites: SITES, windPresets: WIND_PRESETS, stages: STAGES, evacSchemes: EVAC_SCHEMES, supplySchemes: SUPPLY_SCHEMES })
    }
    if (req.method === 'GET' && p === '/api/emergency/reference') return reference ? send(res, 200, reference) : send(res, 404, { error: 'no reference' })
    if (req.method === 'POST' && p === '/api/emergency/simulate') return handleSimulate(req, res, url)
    if (req.method === 'GET') return serveStatic(res, url.pathname)
    send(res, 405, { error: 'method not allowed' })
  } catch (e) {
    send(res, 500, { error: e.message })
  }
})

server.listen(PORT, () => {
  console.log(`[emergency-sim] 服务已启动 http://localhost:${PORT}`)
  console.log(`  数据目录 ${DATA_DIR}${data.roadNetwork ? '（含路网）' : ''}`)
  if (STATIC_DIR) console.log(`  静态文件 ${STATIC_DIR}`)
})
