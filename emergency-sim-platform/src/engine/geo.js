/** 坐标与距离工具（WGS84；局部平面近似，与论文脚本 euclidean_m 一致） */

export const M_PER_DEG_LAT = 110540
const RAD = Math.PI / 180

export function mPerDegLon(lat) {
  return 111320 * Math.cos(lat * RAD)
}

/** 与 Step10/11 LogisticsNode.euclidean_m 相同的近似欧氏距离 (m) */
export function distM(a, b) {
  const dlat = (b.lat - a.lat) * M_PER_DEG_LAT
  const dlon = (b.lon - a.lon) * mPerDegLon(a.lat)
  return Math.hypot(dlat, dlon)
}

/** 论文筛选设施时用的“度距离×111000”（Point.distance*111000），用于复现节点选取规则 */
export function degDistM(a, b) {
  return Math.hypot(a.lon - b.lon, a.lat - b.lat) * 111000
}

/** 以事故点为原点的局部米制坐标系 */
export function makeLocal(lon0, lat0) {
  const kx = mPerDegLon(lat0)
  const ky = M_PER_DEG_LAT
  return {
    lon0, lat0, kx, ky,
    toXY: (lon, lat) => [(lon - lon0) * kx, (lat - lat0) * ky],
    toLL: (x, y) => [x / kx + lon0, y / ky + lat0],
  }
}

/** 方位角（自北顺时针，度） */
export function bearingDeg(x, y) {
  return ((Math.atan2(x, y) / RAD) % 360 + 360) % 360
}

// ---------------- WGS84 <-> GCJ-02（高德/腾讯底图） ----------------
const A = 6378245.0
const EE = 0.00669342162296594323

function outOfChina(lon, lat) {
  return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271
}
function tLat(x, y) {
  let r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x))
  r += ((20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2) / 3
  r += ((20 * Math.sin(y * Math.PI) + 40 * Math.sin((y / 3) * Math.PI)) * 2) / 3
  r += ((160 * Math.sin((y / 12) * Math.PI) + 320 * Math.sin((y * Math.PI) / 30)) * 2) / 3
  return r
}
function tLon(x, y) {
  let r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x))
  r += ((20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2) / 3
  r += ((20 * Math.sin(x * Math.PI) + 40 * Math.sin((x / 3) * Math.PI)) * 2) / 3
  r += ((150 * Math.sin((x / 12) * Math.PI) + 300 * Math.sin((x / 30) * Math.PI)) * 2) / 3
  return r
}

export function wgs84ToGcj02(lon, lat) {
  if (outOfChina(lon, lat)) return [lon, lat]
  let dLat = tLat(lon - 105, lat - 35)
  let dLon = tLon(lon - 105, lat - 35)
  const radLat = lat * RAD
  let magic = Math.sin(radLat)
  magic = 1 - EE * magic * magic
  const sqrtMagic = Math.sqrt(magic)
  dLat = (dLat * 180) / (((A * (1 - EE)) / (magic * sqrtMagic)) * Math.PI)
  dLon = (dLon * 180) / ((A / sqrtMagic) * Math.cos(radLat) * Math.PI)
  return [lon + dLon, lat + dLat]
}

export function gcj02ToWgs84(lon, lat) {
  // 迭代反算，精度 < 1e-7 度
  let x = lon
  let y = lat
  for (let i = 0; i < 6; i++) {
    const [gx, gy] = wgs84ToGcj02(x, y)
    x += lon - gx
    y += lat - gy
  }
  return [x, y]
}
