"""
由论文数据处理流程（scripts/step0~step8）的本地输出，导出平台所需的真实数据
==========================================================================
默认数据（public/data）中的人口栅格为反演近似、地铁站为近似坐标、且不含路网。
在拥有原始数据的电脑上运行本脚本，即可用真实数据替换：

  python tools/export_platform_data.py --research-output "/path/to/1-CSTFM2026会议投稿/output" --out public/data

读取（均为 scripts/config.py 中 DIRS 对应的输出）:
  0_study_area/yizhuang_boundary.shp           → yizhuang_boundary.geojson
  2_poi/{fire_stations,hospitals,shelters,subway_stations}.shp → facilities.json
  8_integrated/scenario_params.json            → 应急仓库（facilities.json.warehouses）
  5_commute/commute_study_area.csv             → 通勤方式构成（私家车数量调整）
  3_population/block_pop_study_area.shp        → population.json（地块标签栅格）
  1_road_network/road_network_graph.gpickle    → road_network.json（可选，--skip-roads 跳过）

输出格式与 tools/build_default_data.py 完全一致，前端/服务端无需改代码；
存在 road_network.json 时引擎自动改用 Dijkstra 路网行程时间。

依赖: geopandas>=0.14 shapely>=2 numpy pandas networkx
"""
import argparse
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

INC_LON, INC_LAT = 116.49401419705991, 39.73559923848592


def log(*a):
    print(*a, flush=True)


def dump(obj, out_dir, name, indent=None):
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, separators=None if indent else (',', ':'))
    log(f'  -> {p} ({os.path.getsize(p) / 1024:.1f} KB)')


def deg_dist_m(lon, lat):
    return np.hypot(np.asarray(lon) - INC_LON, np.asarray(lat) - INC_LAT) * 111000


def read_points(gpd, path, radius_m):
    if not os.path.exists(path):
        log(f'  ⚠️ 缺少 {path}')
        return None
    g = gpd.read_file(path)
    if g.crs is not None and g.crs.to_epsg() != 4326:
        g = g.to_crs(4326)
    g = g[g.geometry.notna()].copy()
    g['lon'] = g.geometry.x
    g['lat'] = g.geometry.y
    if radius_m:
        g = g[deg_dist_m(g['lon'], g['lat']) <= radius_m]
    return g


def col(df, *names):
    """按候选名查找列（兼容 Shapefile 字段名截断为 10 个字符）"""
    for n in names:
        if n in df.columns:
            return n
        if len(n) > 10 and n[:10] in df.columns:
            return n[:10]
    return None


def num(v, default):
    try:
        v = float(v)
        return default if np.isnan(v) else v
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------
def export_boundary(gpd, root, out):
    p = os.path.join(root, '0_study_area', 'yizhuang_boundary.shp')
    if not os.path.exists(p):
        log('  ⚠️ 未找到亦庄控规界，保留现有 yizhuang_boundary.geojson')
        return
    g = gpd.read_file(p).to_crs(4326)
    g['geometry'] = g.geometry.simplify(0.00005, preserve_topology=True)
    gj = json.loads(g[['geometry']].to_json())
    gj['meta'] = {'source': p}
    for i, f in enumerate(gj['features']):
        f['properties'] = {'name': '亦庄控规界' if i == 0 else f'亦庄控规界-{i}'}
    dump(gj, out, 'yizhuang_boundary.geojson')


def export_facilities(gpd, root, out, radius_m):
    poi = os.path.join(root, '2_poi')
    fac = {'meta': {'source': poi, 'crs': 'WGS84 (EPSG:4326)', 'radius_m': radius_m,
                    'notes': ['由 Step3 POI 筛选结果导出，保持原文件顺序（论文按顺序取前 N 个）']}}

    fs = read_points(gpd, os.path.join(poi, 'fire_stations.shp'), radius_m)
    fac['fire_stations'] = [] if fs is None else [
        {'id': f'F{i:04d}', 'name': str(r.get('name', f'消防站{i}')), 'lon': r.lon, 'lat': r.lat, 'type': 'fire_station',
         'stock': {'life_rescue': 50, 'medical': 30, 'protection': 100, 'basic': 200}}
        for i, (_, r) in enumerate(fs.iterrows())]

    hs = read_points(gpd, os.path.join(poi, 'hospitals.shp'), radius_m)
    fac['hospitals'] = [] if hs is None else [
        {'id': f'H{i:04d}', 'name': str(r.get('name', f'医院{i}')), 'lon': r.lon, 'lat': r.lat, 'type': 'hospital',
         'beds': int(num(r.get(col(hs, 'bed_count') or '_'), 200)), 'level': str(r.get(col(hs, 'hospital_level') or '_', '') or '')}
        for i, (_, r) in enumerate(hs.iterrows())]

    sh = read_points(gpd, os.path.join(poi, 'shelters.shp'), radius_m)
    fac['shelters'] = [] if sh is None else [
        {'id': f'R{i:04d}', 'name': str(r.get('name', f'避难所{i}')), 'lon': r.lon, 'lat': r.lat, 'type': 'shelter',
         'capacity': int(num(r.get(col(sh, 'capacity') or '_'), 2000))}
        for i, (_, r) in enumerate(sh.iterrows())]

    sw = read_points(gpd, os.path.join(poi, 'subway_stations.shp'), radius_m)
    fac['subway_stations'] = [] if sw is None else [
        {'id': f'M{i:04d}', 'name': str(r.get(col(sw, 'station_name') or '_') or r.get('name') or f'地铁站{i}'), 'lon': r.lon, 'lat': r.lat,
         'type': 'subway', 'capacity': 8000}
        for i, (_, r) in enumerate(sw.iterrows())]

    sp = os.path.join(root, '8_integrated', 'scenario_params.json')
    whs = []
    if os.path.exists(sp):
        with open(sp, encoding='utf-8') as f:
            whs = json.load(f).get('resources', {}).get('emergency_warehouses', [])
    fac['warehouses'] = [
        {'id': f'W{i:02d}', 'name': w['name'], 'lon': w['lon'], 'lat': w['lat'], 'type': 'warehouse',
         'assumed': '假设' in w['name'], 'stock': {'life_rescue': 200, 'medical': 100, 'protection': 500, 'basic': 1000}}
        for i, w in enumerate(whs)]

    shares = {'car_ratio': 0.30, 'subway_ratio': 0.25, 'bus_ratio': 0.20}
    cp = os.path.join(root, '5_commute', 'commute_study_area.csv')
    if os.path.exists(cp):
        df = pd.read_csv(cp, nrows=10000)
        cols = {'驾车比例': 'car_ratio', '地铁比例': 'subway_ratio', '公交比例': 'bus_ratio', '骑行比例': 'bike_ratio', '步行比例': 'walk_ratio'}
        shares = {en: float(pd.to_numeric(df[cn], errors='coerce').mean()) for cn, en in cols.items() if cn in df.columns} or shares
    fac['commute_mode_shares'] = shares
    log(f'  消防站 {len(fac["fire_stations"])}，医院 {len(fac["hospitals"])}，避难所 {len(fac["shelters"])}，'
        f'地铁站 {len(fac["subway_stations"])}，仓库 {len(fac["warehouses"])}')
    dump(fac, out, 'facilities.json')


def export_population(gpd, root, out, radius_m, cell_m):
    from shapely import contains_xy
    p = os.path.join(root, '3_population', 'block_pop_study_area.shp')
    if not os.path.exists(p):
        log('  ⚠️ 未找到 block_pop_study_area.shp，保留现有 population.json')
        return
    g = gpd.read_file(p)
    if g.crs is not None and g.crs.to_epsg() != 4326:
        g = g.to_crs(4326)
    excl = {'index_right', 'children_ratio', 'elderly_ratio', 'working_age_ratio', 'pop_children', 'pop_elderly', 'pop_working'}
    excl |= {c[:10] for c in excl}
    pop_col = next((c for c in ['pop', 'population', 'POP', 'POPULATION', 'pop_count', 'total', 'Total', 'TOTAL', 'count', 'COUNT', 'num', 'value']
                    if c in g.columns), None)
    if pop_col is None:
        nums = [c for c in g.select_dtypes(include=[np.number]).columns if c not in excl]
        pop_col = nums[0]
    g = g[g.geometry.notna() & (pd.to_numeric(g[pop_col], errors='coerce').fillna(0) > 0)].copy()
    g[pop_col] = pd.to_numeric(g[pop_col], errors='coerce').fillna(0)
    tot = g[pop_col].sum()
    age = {'children': 0.12, 'elderly': 0.15}
    cr, er = col(g, 'children_ratio'), col(g, 'elderly_ratio')
    pc, pe = col(g, 'pop_children'), col(g, 'pop_elderly')
    if cr and er and tot > 0:
        age = {'children': float((g[cr] * g[pop_col]).sum() / tot), 'elderly': float((g[er] * g[pop_col]).sum() / tot)}
    elif pc and pe and tot > 0:
        age = {'children': float(g[pc].sum() / tot), 'elderly': float(g[pe].sum() / tot)}
    log(f'  人口字段 {pop_col}，地块 {len(g)}，总人口 {tot:,.0f}，儿童 {age["children"]:.3f}，老人 {age["elderly"]:.3f}')

    kx = 111320 * np.cos(np.radians(INC_LAT))
    dlon, dlat = cell_m / kx, cell_m / 110540
    if radius_m:
        w, e = INC_LON - radius_m / kx, INC_LON + radius_m / kx
        s, n = INC_LAT - radius_m / 110540, INC_LAT + radius_m / 110540
        g = g.cx[w:e, s:n]
    else:
        w, s, e, n = g.total_bounds
    nx = int(np.ceil((e - w) / dlon))
    ny = int(np.ceil((n - s) / dlat))
    lon0, lat0 = w, n
    labels = np.zeros((ny, nx), dtype=np.int32)
    pops = [0]
    for _, r in g.iterrows():
        geom = r.geometry
        bx0, by0, bx1, by1 = geom.bounds
        c0 = max(0, int((bx0 - lon0) / dlon)); c1 = min(nx - 1, int((bx1 - lon0) / dlon))
        r0 = max(0, int((lat0 - by1) / dlat)); r1 = min(ny - 1, int((lat0 - by0) / dlat))
        if c1 < c0 or r1 < r0:
            continue
        cs = np.arange(c0, c1 + 1); rs = np.arange(r0, r1 + 1)
        X, Y = np.meshgrid(lon0 + (cs + 0.5) * dlon, lat0 - (rs + 0.5) * dlat)
        m = contains_xy(geom, X, Y)
        bid = len(pops)
        sub = labels[r0:r1 + 1, c0:c1 + 1]
        free = m & (sub == 0)
        if free.any():
            sub[free] = bid
        else:  # 小于一个网格的地块：落到代表点所在网格
            pt = geom.representative_point()
            cc = int((pt.x - lon0) / dlon); rr = int((lat0 - pt.y) / dlat)
            if not (0 <= cc < nx and 0 <= rr < ny):
                continue
            if labels[rr, cc] != 0:  # 网格已被占用：并入该地块，避免人口丢失
                pops[labels[rr, cc]] += float(r[pop_col])
                continue
            labels[rr, cc] = bid
        pops.append(float(r[pop_col]))
    flat = labels.ravel()
    change = np.flatnonzero(np.diff(flat)) + 1
    starts = np.concatenate([[0], change])
    runs = np.diff(np.concatenate([starts, [flat.size]]))
    rle = np.empty(starts.size * 2, dtype=np.int64)
    rle[0::2] = flat[starts]; rle[1::2] = runs
    out_obj = {
        'meta': {'description': '地块人口标签栅格：cells 为地块编号（0=无人口），blocks[i] 为地块 i 的常住人口',
                 'source': p, 'approximate': False, 'pop_field': pop_col, 'cell_m': cell_m, 'crs': 'WGS84 (EPSG:4326)'},
        'grid': {'lon0': lon0, 'lat0': lat0, 'dlon': dlon, 'dlat': dlat, 'nx': nx, 'ny': ny,
                 'order': 'row-major, row 0 = 北边界 lat0, 向南递减', 'encoding': 'rle[label,run]'},
        'age_structure': {**age, 'source': 'block_pop_study_area.shp 人口加权平均（七普区县比例）'},
        'blocks': [int(round(v)) for v in pops],
        'cells_rle': [int(v) for v in rle],
    }
    log(f'  栅格 {nx}×{ny}（{cell_m} m），入栅地块 {len(pops) - 1}，人口 {sum(pops):,.0f}')
    dump(out_obj, out, 'population.json')


def export_roads(root, out, radius_m):
    p = os.path.join(root, '1_road_network', 'road_network_graph.gpickle')
    if not os.path.exists(p):
        log('  ⚠️ 未找到 road_network_graph.gpickle，跳过路网（引擎使用几何近似行程时间）')
        return
    import networkx  # noqa: F401  反序列化需要
    with open(p, 'rb') as f:
        G = pickle.load(f)
    idx = {}
    nodes = []
    edges = []
    for u, v, d in G.edges(data=True):
        if radius_m and (deg_dist_m(u[0], u[1]) > radius_m or deg_dist_m(v[0], v[1]) > radius_m):
            continue
        for node in (u, v):
            if node not in idx:
                idx[node] = len(idx)
                nodes += [round(float(node[0]), 6), round(float(node[1]), 6)]
        length = float(d.get('length_m', 0) or 0)
        speed = float(d.get('speed_kmh', 0) or 0)
        if speed <= 0 and d.get('freeflow_time_s'):
            speed = length / float(d['freeflow_time_s']) * 3.6
        edges += [idx[u], idx[v], round(length, 1), round(speed or 30, 1)]
    obj = {'meta': {'source': p, 'radius_m': radius_m, 'format': 'nodes=[lon,lat,...]; edges=[u,v,length_m,speed_kmh,...]（有向）'},
           'nodes': nodes, 'edges': edges}
    log(f'  路网节点 {len(idx)}，有向边 {len(edges) // 4}')
    dump(obj, out, 'road_network.json')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--research-output', required=True, help='scripts/config.py 中 OUTPUT_DIR（含 0_study_area/、2_poi/ 等子目录）')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'public', 'data'))
    ap.add_argument('--radius-km', type=float, default=25, help='以太和桥为中心的裁剪半径，0=不裁剪')
    ap.add_argument('--cell-m', type=float, default=75, help='人口栅格分辨率 (m)')
    ap.add_argument('--skip-roads', action='store_true')
    a = ap.parse_args()
    import geopandas as gpd
    root = a.research_output
    if not os.path.isdir(root):
        sys.exit(f'目录不存在：{root}')
    radius_m = a.radius_km * 1000
    log('[1/4] 亦庄控规界'); export_boundary(gpd, root, a.out)
    log('[2/4] 应急设施'); export_facilities(gpd, root, a.out, radius_m)
    log('[3/4] 地块人口'); export_population(gpd, root, a.out, radius_m, a.cell_m)
    log('[4/4] 路网'); (log('  已跳过') if a.skip_roads else export_roads(root, a.out, radius_m))
    log('完成。重新构建或直接刷新页面即可使用新数据（服务端需重启）。')


if __name__ == '__main__':
    main()
