/**
 * 模型默认参数 —— 与论文（CSTFM 2026, CT007）及 scripts/step9~step12 保持一致。
 * 所有坐标 WGS84；距离单位 m；时间单位 min（另有注明除外）。
 */

export const ENGINE_VERSION = '1.0.0'

/** 气体毒性阈值 (mg/m³)，Step9 gas_thresholds */
export const GAS_THRESHOLDS = {
  氯气: { IDLH: 29.0, ERPG3: 20.0, ERPG2: 3.0, ERPG1: 1.0, detection: 0.5 },
  氨气: { IDLH: 210.0, ERPG3: 750.0, ERPG2: 150.0, ERPG1: 25.0, detection: 5.0 },
}

/** 事故发生地预设（可在此追加六环沿线其他点位） */
export const SITES = [
  {
    id: 'taihe',
    name: '太和桥',
    desc: '六环太和桥立交（论文基准场景）',
    lon: 116.49401419705991,
    lat: 39.73559923848592,
  },
]

/** 风况预设：风向为气象学约定（风的来向，0=北风，225=西南风） */
export const WIND_PRESETS = [
  { id: 'sw2', name: '二级西南风', speed: 3.0, dir: 225, stability: 'D', note: '论文基准 3.0 m/s' },
  { id: 'sw3', name: '三级西南风', speed: 4.4, dir: 225, stability: 'D', note: '4.4 m/s' },
  { id: 'n2', name: '二级北风', speed: 3.0, dir: 0, stability: 'D', note: '风向敏感性' },
  { id: 'e2', name: '二级东风', speed: 3.0, dir: 90, stability: 'D', note: '风向敏感性' },
  { id: 'sw5', name: '五级西南风', speed: 8.0, dir: 225, stability: 'D', note: '强风 8.0 m/s' },
  { id: 'sw1f', name: '一级静稳风', speed: 1.5, dir: 225, stability: 'F', note: '夜间稳定层结，最不利' },
  { id: 'sw7', name: '七级西南风', speed: 15.0, dir: 225, stability: 'D', note: '>6级，无人机停飞' },
]

/** 物资分类，Step10 SUPPLY_CATEGORIES */
export const SUPPLY_CATEGORIES = {
  life_rescue: { name: '生命救援类', items: '防毒面具、氧气瓶、急救药品、解毒剂', priority: 1, unitKg: 3.0, windowMin: 30, hard: true, penaltyPerMin: 1000, color: '#ff4d4f' },
  medical: { name: '医疗支援类', items: '担架、医疗设备、血浆、输液', priority: 2, unitKg: 8.0, windowMin: 60, hard: true, penaltyPerMin: 500, color: '#ff8a3d' },
  protection: { name: '防护设备类', items: '防护服、隔离带、警示设备', priority: 3, unitKg: 5.0, windowMin: 120, hard: false, penaltyPerMin: 100, color: '#ffd23f' },
  basic: { name: '基础保障类', items: '饮用水、食品、帐篷、照明设备', priority: 4, unitKg: 15.0, windowMin: 240, hard: false, penaltyPerMin: 10, color: '#4fd2ff' },
}
export const SUPPLY_KEYS = ['life_rescue', 'medical', 'protection', 'basic']

/** 人群分类，Step11 POP_CLASSES */
export const POP_CLASSES = {
  1: { name: '重伤/中毒者', weight: 10, dest: 'hospital', modes: ['ambulance', 'helicopter'], color: '#ff4d4f' },
  2: { name: '老人/儿童/残障', weight: 5, dest: 'hospital_or_shelter', modes: ['ambulance', 'helicopter', 'bus', 'car', 'subway'], color: '#ffb020' },
  3: { name: '一般健康人员', weight: 1, dest: 'shelter', modes: ['bus', 'car', 'subway'], color: '#4fd2ff' },
}

/** 疏散交通工具，Step11 VEHICLE_MODES_DEFAULT；travel: ground=道路, air=直线飞行, rail=轨道 */
export const VEHICLE_MODES = {
  ambulance: { name: '救护车', capacity: 3, speedKmh: 50, count: 15, travel: 'ground', color: '#ff5c7a' },
  helicopter: { name: '直升机', capacity: 6, speedKmh: 150, count: 3, travel: 'air', color: '#c77dff' },
  bus: { name: '公交车', capacity: 50, speedKmh: 30, count: 20, travel: 'ground', color: '#3ddc97' },
  car: { name: '私家车', capacity: 4, speedKmh: 35, count: 100, travel: 'ground', color: '#a0b4c8' },
  subway: { name: '地铁', capacity: 1200, speedKmh: 40, count: 15, travel: 'rail', color: '#2f7bff' },
}
export const MODE_KEYS = ['ambulance', 'helicopter', 'bus', 'car', 'subway']

/** 就地避难物资需求率（每 1000 人），Step10 SHELTER_SUPPLY_RATES */
export const SHELTER_SUPPLY_RATES = {
  erpg2_k3: { life_rescue: 0, medical: 5, protection: 200, basic: 100 },
  erpg1_k2: { life_rescue: 0, medical: 3, protection: 100, basic: 80 },
  erpg1_k3: { life_rescue: 0, medical: 0, protection: 50, basic: 60 },
}

export const ZONE_KEYS = ['erpg3', 'erpg2', 'erpg1']
export const ZONE_NAMES = { erpg3: 'ERPG-3 核心危险区', erpg2: 'ERPG-2 警戒区', erpg1: 'ERPG-1 影响区' }

/** 分区差异化疏散规则，Step11 EVAC_RULES：true=疏散，false=就地避难 */
export const EVAC_RULES = {
  erpg3: { 1: true, 2: true, 3: true },
  erpg2: { 1: true, 2: true, 3: false },
  erpg1: { 1: true, 2: false, 3: false },
}

export const SECTOR_NAMES = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']

export const DEFAULT_PARAMS = {
  method: 'dual', // dual=双链协同（疏散→就地避难需求→物资）；evac=仅疏散；supply=仅物资（不含就地避难需求）
  algorithm: 'two_stage', // two_stage=贪心+2-opt（论文）；two_stage_direct=直送优先改进；greedy=仅贪心构造
  solver: 'local', // local=浏览器 Web Worker；remote=服务端 REST API

  siteId: 'taihe',
  incident: { lon: SITES[0].lon, lat: SITES[0].lat, name: SITES[0].name },
  windPresetId: 'sw2',

  gas: '氯气',
  leakRateKgMin: 5,
  leakDurationMin: 60,
  releaseHeightM: 2.0,
  windSpeed: 3.0,
  windDir: 225,
  stability: 'D',

  plume: { extentM: 10000, cellM: 50 },
  zoneMode: 'buffered', // buffered=等值线+缓冲（论文实际采用）；contour=原始等值线；auto=论文级联策略
  zoneBuffersM: { erpg3: 500, erpg2: 1500, erpg1: 3000 },

  roads: {
    closureRadiusM: 1000,
    congestionRadiusM: 3000,
    influenceRadiusM: 5000,
    bprAlpha: 0.15,
    bprBeta: 4.0,
    vc: 0.8,
    circuity: 1.3, // 无路网时：路网绕行系数
    closureAccessKmh: 20, // 无路网时：封闭区内应急通行速度
    vehicleSpeedCap: true, // 有路网时：边速度取 min(道路限速, 车辆速度)；false 复现 network_router.py（仅用道路自由流速度）
    snapToMainComponent: false, // 有路网时：点位只吸附到封闭后的最大强连通分量并补接入段；false 与论文一致（吸附最近节点）
  },

  population: { mode: 'intersect', k1Ratio: 0.02 },

  // 动态风险暴露 ρ(i,t)：nominalByZone=分区内人员按所在 ERPG 区阈值浓度计（与局部平均浓度取大）；
  // dynamic=泄漏停止且烟羽过境后（t > 泄漏时长 + r/u）风险归零
  risk: { nominalByZone: true, dynamic: true }, // intersect=地块相交（论文 gpd.clip 口径）；area=面积加权

  evacuation: {
    Tmax: 180,
    dt: 5,
    flexiblePriority: true,
    k3ReservedRatio: 0.25,
    unloadMin: 2,
    fleet: {
      ambulance: 15,
      helicopter: 3,
      bus: 20,
      car: null, // null = 按通勤驾车比例自动：max(20, int(100*car_ratio/0.30))
      subway: 15,
    },
    weights: { z1: 1.0, z2: 0.01, z3: 100.0 },
    pUnsat: 500,
    sensitivityAmbulances: [5, 10, 15, 20, 30, 40, 50],
    hospitalRangeM: [2000, 12000],
    shelterRangeM: [2000, 12000],
    subwayRangeM: [1500, 8000],
    maxHospitals: 12,
    maxShelters: 15,
    maxSubways: 8,
  },

  supply: {
    trucks: 20,
    drones: 10,
    truckSpeedKmh: 40,
    truckCapKg: 2000,
    droneSpeedKmh: 60,
    droneMaxKg: 25,
    droneRangeM: 15000,
    droneLoadMin: 5,
    unloadMin: 5,
    droneMaxWindMs: 13.8, // 风力 >6 级（≥13.9 m/s）无人机停飞
    weights: { makespan: 1.0, penalty: 1.0, unmet: 10000.0 },
    maxIter: 200,
    supplyRangeM: [1000, 15000],
    maxFireStations: 8,
    relayRangeM: [2000, 6000],
    relayMinCapacity: 2000,
    maxRelays: 6,
    hospitalDemandRangeM: [2000, 10000],
    maxDemandNodes: 15,
    shelterDemandNodes: { erpg2: 4, erpg1: 6 },
    sensitivityDrones: [0, 5, 10, 15, 20, 30, 40],
  },

  stageDelayMs: 0,
}

/** 深合并（数组整体替换） */
export function mergeParams(base, patch) {
  if (patch === undefined || patch === null) return structuredClone(base)
  if (typeof base !== 'object' || base === null || Array.isArray(base)) return structuredClone(patch)
  const out = structuredClone(base)
  for (const [k, v] of Object.entries(patch)) {
    out[k] = k in base && typeof base[k] === 'object' && base[k] !== null && !Array.isArray(base[k]) && typeof v === 'object' && v !== null && !Array.isArray(v)
      ? mergeParams(base[k], v)
      : structuredClone(v)
  }
  return out
}

/** 由站点/风况预设得到完整参数 */
export function paramsFromPresets({ siteId, windPresetId, incident } = {}, base = DEFAULT_PARAMS) {
  const p = structuredClone(base)
  const site = SITES.find((s) => s.id === siteId)
  if (site) {
    p.siteId = site.id
    p.incident = { lon: site.lon, lat: site.lat, name: site.name }
  } else if (incident) {
    p.siteId = 'custom'
    p.incident = { ...incident }
  }
  const w = WIND_PRESETS.find((x) => x.id === windPresetId)
  if (w) {
    p.windPresetId = w.id
    p.windSpeed = w.speed
    p.windDir = w.dir
    p.stability = w.stability
  }
  return p
}

/** 蒲福风级 */
export function beaufort(ms) {
  const edges = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]
  let lv = 0
  while (lv < edges.length && ms >= edges[lv]) lv++
  return lv
}

export function windDirName(deg) {
  const names = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
  return names[Math.round((((deg % 360) + 360) % 360) / 45) % 8] + '风'
}
