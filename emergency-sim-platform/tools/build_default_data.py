"""
从本仓库已有的研究成果生成平台默认数据（public/data/*.json）
================================================================
输入（均位于仓库内）:
  1-CSTFM2026会议投稿/技术路线图/10_supply_optimization/supply_optimization_results.json
  1-CSTFM2026会议投稿/技术路线图/11_evacuation_optimization/evacuation_results.json
  1-CSTFM2026会议投稿/技术路线图/12_analysis/paper_summary_tables.json
  1-CSTFM2026会议投稿/技术路线图/9_scenario/scenario_results.json
  1-CSTFM2026会议投稿/技术路线图/9_scenario/danger_zones.shp
  1-CSTFM2026会议投稿/figures/step4_population.png

输出:
  public/data/facilities.json          应急设施池（消防站/仓库/避难所/医院/地铁站）
  public/data/population.json          地块人口栅格（标签栅格 + 地块人口）
  public/data/yizhuang_boundary.geojson 亦庄控规界
  public/data/paper_reference.json     论文基准结果（用于对照）

说明:
  原始地块人口(Block_population.shp)与 POI 全集不在仓库中。本脚本从 Step4 人口分布图
  反演地块人口（YlOrRd 色带 + alpha=0.7 逆映射，连通域分割地块），再以论文 ERPG 分区
  人口（Step11: ERPG-2 19,657 人, ERPG-1 407,115 人）做全局比例标定。
  拿到原始数据后请改用 tools/export_platform_data.py 生成真实数据，覆盖本脚本输出。

依赖: numpy scipy pillow matplotlib pyshp shapely
用法: python tools/build_default_data.py  （在 emergency-sim-platform/ 目录下运行）
"""
import json
import os
import sys
import warnings

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree
import matplotlib
import shapefile
from shapely.geometry import shape, Polygon, mapping
from shapely.ops import transform, unary_union
from shapely import contains_xy

warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM = os.path.dirname(HERE)
REPO = os.path.dirname(PLATFORM)
RES = os.path.join(REPO, '1-CSTFM2026会议投稿', '技术路线图')
FIG = os.path.join(REPO, '1-CSTFM2026会议投稿', 'figures')
OUT = os.path.join(PLATFORM, 'public', 'data')

INC_LON, INC_LAT = 116.49401419705991, 39.73559923848592
KX = 111320 * np.cos(np.radians(INC_LAT))
KY = 110540

# ---- Step4 图的地理配准（原图像素，由经纬网格线定位）----
X0, PX_LON = 716.5, 1143.33      # 116.2°E 的 x 像素, 每度经度像素数
Y0, PX_LAT = 466.5, 1487.5       # 39.9°N 的 y 像素, 每度纬度像素数
VMIN, VMAX = 30.0, 92690.0       # 色带范围（由色带刻度 20k/40k/60k/80k 推算）

# 平台人口栅格范围（覆盖亦庄控规界及其外围）
CROP = dict(lon_min=116.30, lon_max=116.72, lat_min=39.58, lat_max=39.90)


def load_json(*parts):
    with open(os.path.join(*parts), 'r', encoding='utf-8') as f:
        return json.load(f)


def dump(obj, name, indent=None):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, separators=None if indent else (',', ':'))
    print(f'  -> {os.path.relpath(path, PLATFORM)} ({os.path.getsize(path)/1024:.1f} KB)')


def to_m(g):
    return transform(lambda x, y, z=None: ((np.asarray(x) - INC_LON) * KX, (np.asarray(y) - INC_LAT) * KY), g)


def to_ll(g):
    return transform(lambda x, y, z=None: (np.asarray(x) / KX + INC_LON, np.asarray(y) / KY + INC_LAT), g)


# =====================================================================
# 1. 应急设施
# =====================================================================
def build_facilities():
    print('[1/4] 应急设施池')
    sup = load_json(RES, '10_supply_optimization', 'supply_optimization_results.json')
    evac = load_json(RES, '11_evacuation_optimization', 'evacuation_results.json')
    net = sup['logistics_network']

    fire, warehouses = [], []
    for i, n in enumerate(net['supply_nodes']):
        rec = {'id': f'S{i+1:02d}', 'name': n['name'], 'lon': n['lon'], 'lat': n['lat']}
        if n['name'].startswith('假设仓库'):
            rec.update(type='warehouse', assumed=True,
                       stock={'life_rescue': 200, 'medical': 100, 'protection': 500, 'basic': 1000})
            warehouses.append(rec)
        else:
            rec.update(type='fire_station',
                       stock={'life_rescue': 50, 'medical': 30, 'protection': 100, 'basic': 200})
            fire.append(rec)

    shelters = [{'id': f'R{i+1:02d}', 'name': n['name'], 'lon': n['lon'], 'lat': n['lat'],
                 'type': 'shelter', 'capacity': 2000, 'relay_candidate': True,
                 'capacity_note': 'Step10 以 >2000 人筛选为中转站，取下限 2000'}
                for i, n in enumerate(net['relay_nodes'])]

    hospitals = []
    for n in net['demand_nodes']:
        if any(k in n['name'] for k in ('医院', '卫生')) and '避难' not in n['name']:
            hospitals.append({'id': f'H{len(hospitals)+1:02d}', 'name': n['name'], 'lon': n['lon'],
                              'lat': n['lat'], 'type': 'hospital', 'beds': 200,
                              'beds_note': '原 POI 无床位字段，按 Step11 默认 200'})

    # 亦庄线等站点：仓库内无坐标，以下为近似坐标（需用导出脚本替换为 POI 真实坐标）
    subway = [
        ('亦庄桥', 116.4868, 39.8031), ('万源街', 116.5035, 39.8007), ('荣京东街', 116.5129, 39.7934),
        ('荣昌东街', 116.5220, 39.7846), ('同济南路', 116.5398, 39.7759), ('经海路', 116.5573, 39.7834),
        ('瀛海', 116.4405, 39.7608), ('德茂', 116.4272, 39.7795),
    ]
    subway = [{'id': f'M{i+1:02d}', 'name': f'{nm}站', 'lon': lo, 'lat': la, 'type': 'subway',
               'capacity': 8000, 'approx': True} for i, (nm, lo, la) in enumerate(subway)]

    out = {
        'meta': {
            'source': 'Step10/Step11 输出 (supply_optimization_results.json / evacuation_results.json)',
            'crs': 'WGS84 (EPSG:4326)',
            'notes': [
                '消防站/仓库/避难所/医院坐标取自论文 Step10 物流网络节点，为原始 POI 坐标。',
                '地铁站坐标为近似值（仓库内无 subway_stations.shp），标记 approx=true，请用导出脚本替换。',
                '避难所容量、医院床位按论文代码默认/下限取值。',
            ],
        },
        'fire_stations': fire,
        'warehouses': warehouses,
        'shelters': shelters,
        'hospitals': hospitals,
        'subway_stations': subway,
        'commute_mode_shares': evac['commute_mode_shares'],
    }
    print(f'  消防站 {len(fire)}, 仓库 {len(warehouses)}, 避难所 {len(shelters)}, '
          f'医院 {len(hospitals)}, 地铁站 {len(subway)}(近似)')
    dump(out, 'facilities.json', indent=1)


# =====================================================================
# 2. 人口栅格（由 Step4 图反演 + 标定）
# =====================================================================
def segment_blocks(src):
    im = np.asarray(Image.open(src).convert('RGB')).astype(float)
    xa = int(round(X0 + (CROP['lon_min'] - 116.2) * PX_LON))
    xb = int(round(X0 + (CROP['lon_max'] - 116.2) * PX_LON))
    ya = int(round(Y0 + (39.9 - CROP['lat_max']) * PX_LAT))
    yb = int(round(Y0 + (39.9 - CROP['lat_min']) * PX_LAT))
    sub = im[ya:yb, xa:xb]
    lut = matplotlib.colormaps['YlOrRd'](np.linspace(0, 1, 512))[:, :3] * 255
    tree = cKDTree(0.7 * lut + 0.3 * 255)              # geopandas plot alpha=0.7 叠加白底
    d, idx = tree.query(sub.reshape(-1, 3))
    d = d.reshape(sub.shape[:2]); idx = idx.reshape(sub.shape[:2])
    white = sub.min(-1) > 252
    valid = (d < 5.0) & ~white

    def mode_filter(win):
        w = win[win >= 0]
        if len(w) == 0:
            return -1
        vals, cnt = np.unique(w, return_counts=True)
        return vals[np.argmax(cnt)]

    # 叠加线（经纬网、边界线、五角星）穿过的像素：用邻域众数回填，避免把地块切碎
    q = np.where(valid, idx, -1)
    gap = ~valid & ~white
    for _ in range(4):
        fill = ndimage.generic_filter(q, mode_filter, size=3, mode='constant', cval=-1)
        upd = gap & (q < 0) & (fill >= 0)
        if not upd.any():
            break
        q[upd] = fill[upd]

    labels = np.zeros(q.shape, dtype=np.int32)
    pops = [0.0]
    for k in np.unique(q[q >= 0]):
        lab, n = ndimage.label(q == k)
        if n == 0:
            continue
        sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
        val = VMIN + k / 511 * (VMAX - VMIN)
        for i in range(n):
            if sizes[i] < 3:
                continue
            labels[lab == i + 1] = len(pops)
            pops.append(val)
    lon0 = 116.2 + (xa - X0) / PX_LON
    lat0 = 39.9 - (ya - Y0) / PX_LAT
    return labels, np.array(pops), lon0, lat0


def build_population():
    print('[2/4] 人口栅格')
    labels, pops, lon0, lat0 = segment_blocks(os.path.join(FIG, 'step4_population.png'))
    ny, nx = labels.shape
    dlon, dlat = 1 / PX_LON, 1 / PX_LAT
    # 重新编号（去掉无像素的地块）
    used = np.unique(labels)
    used = used[used > 0]
    remap = np.zeros(int(labels.max()) + 1, dtype=np.int32)
    remap[used] = np.arange(1, len(used) + 1)
    labels = remap[labels]
    pops = np.concatenate([[0.0], pops[used]])

    # ---- 标定：与论文 Step11 ERPG 分区人口（地块相交口径，同 gpd.clip）对齐 ----
    lon = lon0 + (np.arange(nx) + 0.5) * dlon
    lat = lat0 - (np.arange(ny) + 0.5) * dlat
    LON, LAT = np.meshgrid(lon, lat)
    MX, MY = (LON - INC_LON) * KX, (LAT - INC_LAT) * KY
    r = shapefile.Reader(os.path.join(RES, '9_scenario', 'danger_zones.shp'), encoding='utf-8')
    g = {sr.record[0]: to_m(shape(sr.shape.__geo_interface__)) for sr in r.iterShapeRecords()}
    e3 = g['core_danger'].buffer(500)
    e2 = g['warning'].buffer(1500).difference(e3)
    e1 = g['influence'].buffer(3000).difference(g['warning'].buffer(1500))

    def inter_pop(poly, p):
        ids = np.unique(labels[contains_xy(poly, MX, MY)])
        return float(p[ids[ids > 0]].sum())

    target = 19657 + 407115
    raw = inter_pop(e2, pops) + inter_pop(e1, pops)
    scale = target / raw
    pops_s = np.round(pops * scale)
    check = {
        'erpg3_buffer': (inter_pop(e3, pops_s), 0),
        'erpg2_ring': (inter_pop(e2, pops_s), 19657),
        'erpg1_ring': (inter_pop(e1, pops_s), 407115),
        'circle_1km': (inter_pop(g['closure_1km'], pops_s), 632),
        'circle_3km': (inter_pop(g['congestion_3km'], pops_s), 156340),
        'circle_5km': (inter_pop(g['influence_5km'], pops_s), 488211),
    }
    print(f'  地块 {len(pops)-1}, 栅格 {nx}x{ny} (~{dlon*KX:.0f}m), 标定系数 {scale:.4f}')
    for k, (v, p) in check.items():
        print(f'    {k:14s} 平台 {v:>9,.0f}   论文 {p:>9,}')

    # 行优先游程编码 [label, run, label, run, ...]
    flat = labels.ravel()
    change = np.flatnonzero(np.diff(flat)) + 1
    starts = np.concatenate([[0], change])
    runs = np.diff(np.concatenate([starts, [flat.size]]))
    rle = np.empty(starts.size * 2, dtype=np.int64)
    rle[0::2] = flat[starts]; rle[1::2] = runs

    out = {
        'meta': {
            'description': '地块人口标签栅格：cells 为地块编号（0=无人口），blocks[i] 为地块 i 的常住人口',
            'source': '由 figures/step4_population.png 反演（YlOrRd 色带逆映射 + 连通域分割），'
                      '按论文 Step11 ERPG-2/ERPG-1 分区人口做全局比例标定',
            'approximate': True,
            'replace_with': 'tools/export_platform_data.py（读取 output/3_population/block_pop_study_area.shp）',
            'calibration': {
                'method': 'scale = (19,657 + 407,115) / 反演人口(ERPG-2环 + ERPG-1环, 地块相交口径)',
                'scale': round(scale, 5),
                'check_platform_vs_paper': {k: [round(v), p] for k, (v, p) in check.items()},
            },
            'crs': 'WGS84 (EPSG:4326)',
        },
        'grid': {'lon0': lon0, 'lat0': lat0, 'dlon': dlon, 'dlat': dlat, 'nx': nx, 'ny': ny,
                 'order': 'row-major, row 0 = 北边界 lat0, 向南递减', 'encoding': 'rle[label,run]'},
        'age_structure': {'children': 0.12, 'elderly': 0.15,
                          'source': '七普大兴区/通州区年龄结构（论文 2.3.3 节）'},
        'blocks': [int(v) for v in pops_s],
        'cells_rle': [int(v) for v in rle],
    }
    dump(out, 'population.json')


# =====================================================================
# 3. 亦庄控规界（由 Step4 图中橙色边界线数字化）
# =====================================================================
def build_boundary():
    print('[3/4] 亦庄控规界')
    im = np.asarray(Image.open(os.path.join(FIG, 'step4_population.png')).convert('RGB')).astype(float)
    xa, xb = int(X0 - 0.02 * PX_LON), int(X0 + 0.68 * PX_LON)
    ya, yb = int(Y0 - 0.10 * PX_LAT), int(Y0 + 0.43 * PX_LAT)
    sub = im[ya:yb, xa:xb]
    target = np.array([0xE6, 0x51, 0x00], dtype=float)
    line = np.linalg.norm(sub - target, axis=-1) < 60
    line = ndimage.binary_closing(line, iterations=2)
    filled = ndimage.binary_fill_holes(line)
    filled = ndimage.binary_erosion(filled, iterations=2) | (filled & ~line)
    lab, n = ndimage.label(filled)
    sizes = ndimage.sum(filled, lab, index=np.arange(1, n + 1))
    import contourpy
    polys = []
    for i in np.argsort(sizes)[::-1]:
        if sizes[i] < 150:
            break
        m = (lab == i + 1).astype(float)
        m = np.pad(m, 1)
        gen = contourpy.contour_generator(z=m)
        for line_xy in gen.lines(0.5):
            if len(line_xy) < 10:
                continue
            xs = line_xy[:, 0] - 1 + xa
            ys = line_xy[:, 1] - 1 + ya
            lon = 116.2 + (xs - X0) / PX_LON
            lat = 39.9 - (ys - Y0) / PX_LAT
            p = Polygon(np.c_[lon, lat]).buffer(0)
            if p.area > 0:
                polys.append(p)
    merged = unary_union(polys).simplify(0.0004, preserve_topology=True)
    if merged.geom_type == 'Polygon':
        merged = [merged]
    else:
        merged = list(merged.geoms)
    merged.sort(key=lambda p: -p.area)
    feats = [{'type': 'Feature', 'properties': {'name': '亦庄控规界' if i == 0 else f'亦庄控规界-飞地{i}'},
              'geometry': mapping(p)} for i, p in enumerate(merged)]
    gj = {'type': 'FeatureCollection',
          'meta': {'source': '由 figures/step4_population.png 中的控规界线数字化（约 75m 精度）',
                   'replace_with': 'output/0_study_area/yizhuang_boundary.shp'},
          'features': feats}
    # 坐标保留 5 位小数
    for f in gj['features']:
        f['geometry'] = json.loads(json.dumps(f['geometry']), parse_float=lambda s: round(float(s), 5))
    areas = [to_m(p).area / 1e6 for p in merged]
    print(f'  多边形 {len(merged)} 个, 面积 {", ".join(f"{a:.1f}" for a in areas)} km²')
    dump(gj, 'yizhuang_boundary.geojson')


# =====================================================================
# 4. 论文基准结果
# =====================================================================
def build_reference():
    print('[4/4] 论文基准结果')
    sup = load_json(RES, '10_supply_optimization', 'supply_optimization_results.json')
    evac = load_json(RES, '11_evacuation_optimization', 'evacuation_results.json')
    scen = load_json(RES, '9_scenario', 'scenario_results.json')
    summ = load_json(RES, '12_analysis', 'final_summary.json')

    r = shapefile.Reader(os.path.join(RES, '9_scenario', 'danger_zones.shp'), encoding='utf-8')
    feats = []
    for sr in r.iterShapeRecords():
        geom = json.loads(json.dumps(sr.shape.__geo_interface__), parse_float=lambda s: round(float(s), 6))
        feats.append({'type': 'Feature', 'properties': {'zone': sr.record[0]}, 'geometry': geom})

    sc = sup['scenario_comparison']
    ev = evac['comparison']
    ref = {
        'meta': {'description': '论文（CSTFM 2026, CT007）Step9–12 输出的基准场景结果，'
                                '平台在“太和桥 + 二级西南风 3.0m/s”基准场景下与之对照',
                 'source': '1-CSTFM2026会议投稿/技术路线图/*'},
        'incident': scen['incident'],
        'road_impacts_km': {k: round(v['total_km'], 2) for k, v in scen['road_impacts'].items()},
        'affected_population_circles': {k: v['total'] for k, v in scen['affected_population'].items()},
        'erpg_zone_populations': {k: round(v['total']) for k, v in evac['erpg_zone_populations'].items()},
        'shelter_in_place': evac['shelter_in_place']['shelter_in_place_population'],
        'supply': {k: {kk: v[kk] for kk in ('label', 'total_tasks', 'completed_tasks', 'unmet_tasks',
                                            'makespan_min', 'avg_delivery_time_min', 'total_penalty',
                                            'route_types', 'by_category')}
                   for k, v in sc.items()},
        'supply_sensitivity_drones': sup['sensitivity_drone_count'],
        'evacuation': {k: {kk: v[kk] for kk in ('label', 'evacuated', 'remaining', 'evac_rate', 'by_class',
                                                'by_mode', 'by_zone', 'total_risk')}
                       for k, v in ev.items()},
        'evacuation_sensitivity_ambulance': evac['sensitivity_ambulance'],
        'evacuation_timeline_baseline': evac['timelines']['baseline'],
        'resilience': summ['resilience'],
        'danger_zones': {'type': 'FeatureCollection', 'features': feats},
    }
    dump(ref, 'paper_reference.json')


if __name__ == '__main__':
    build_facilities()
    build_population()
    build_boundary()
    build_reference()
    print('完成')
