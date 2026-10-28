"""
由论文数据处理流程（scripts/step0~step8）的本地输出，导出平台所需的真实数据
==========================================================================
默认数据（public/data）中的人口栅格为反演近似、地铁站为近似坐标、且不含路网。
在拥有原始数据的电脑上运行本脚本，即可用真实数据替换：

  python tools/export_platform_data.py --research-output "/path/to/1-CSTFM2026会议投稿/output" --check   # 先检查输入
  python tools/export_platform_data.py --research-output "/path/to/1-CSTFM2026会议投稿/output"           # 导出

--research-output 也可以给上一级目录，脚本会在其子目录中自动查找下列文件。
找不到任何核心输入时不写入任何文件；覆盖前会把原文件备份到 data_backup/<时间戳>/（--backup-dir 可改）。

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
import shutil
import sys
import time

import numpy as np
import pandas as pd

INC_LON, INC_LAT = 116.49401419705991, 39.73559923848592


def log(*a):
    print(*a, flush=True)


# key: (期望相对路径, 生成该文件的论文脚本, 该脚本依赖的原始数据（scripts/config.py）, 是否核心输入)
INPUTS = {
    'boundary': ('0_study_area/yizhuang_boundary.shp', 'step0_study_area.py', 'YIZHUANG_BOUNDARY_SHP', True),
    'roads': ('1_road_network/road_network_graph.gpickle', 'step2_road_network.py', 'OSM_ROAD_SHP', True),
    'fire_stations': ('2_poi/fire_stations.shp', 'step3_poi_filter.py', 'POI_FILE', True),
    'hospitals': ('2_poi/hospitals.shp', 'step3_poi_filter.py', 'POI_FILE', True),
    'shelters': ('2_poi/shelters.shp', 'step3_poi_filter.py', 'POI_FILE', True),
    'subway_stations': ('2_poi/subway_stations.shp', 'step3_poi_filter.py', 'POI_FILE', True),
    'population': ('3_population/block_pop_study_area.shp', 'step4_population.py', 'BLOCK_POP_SHP, CENSUS_SHP', True),
    'commute': ('5_commute/commute_study_area.csv', 'step5_od_clip.py', 'COMMUTE_FILE', False),
    'scenario_params': ('8_integrated/scenario_params.json', 'step8_integration.py', '（前序步骤输出）', False),
}
SKIP_DIRS = {'node_modules', '.git', 'dist', '__pycache__', 'figures', 'tmp', '_backup', 'emergency-sim-platform'}


def _valid(path):
    if not os.path.isfile(path):
        return False
    if path.lower().endswith('.shp'):  # Shapefile 需要同名 .dbf/.shx
        stem = path[:-4]
        return all(os.path.exists(stem + ext) or os.path.exists(stem + ext.upper()) for ext in ('.dbf', '.shx'))
    return True


def locate_inputs(root, max_depth=6):
    """先按 output/ 标准结构查找；找不到则在 root（及其上一级，若 root 名为 output）下递归按文件名搜索"""
    found = {k: os.path.join(root, rel) for k, (rel, *_) in INPUTS.items() if _valid(os.path.join(root, rel))}
    missing = {k for k in INPUTS if k not in found}
    if not missing:
        return found
    roots = [root]
    if os.path.basename(os.path.normpath(root)) == 'output':
        roots.append(os.path.dirname(os.path.normpath(root)))
    names = {os.path.basename(INPUTS[k][0]): k for k in missing}
    cands = {k: [] for k in missing}
    seen = set()
    for r in roots:
        base_depth = os.path.normpath(r).count(os.sep)
        for d, dirs, files in os.walk(r):
            real = os.path.realpath(d)
            if real in seen:
                dirs[:] = []
                continue
            seen.add(real)
            dirs[:] = [x for x in dirs if not x.startswith('.') and x not in SKIP_DIRS]
            if os.path.normpath(d).count(os.sep) - base_depth >= max_depth:
                dirs[:] = []
            for f in files:
                if f in names and _valid(os.path.join(d, f)):
                    cands[names[f]].append(os.path.join(d, f))
    for k, lst in cands.items():
        if not lst:
            continue
        sub = os.path.dirname(INPUTS[k][0])
        # 优先目录名与标准结构一致者，其次最新修改
        lst.sort(key=lambda p: (os.path.basename(os.path.dirname(p)) == sub, os.path.getmtime(p)), reverse=True)
        found[k] = lst[0]
    return found


def describe_dir(root, limit=40):
    """列出目录下各子目录的文件数，帮助定位问题"""
    rows = []
    try:
        entries = sorted(os.listdir(root))
    except OSError as e:
        return [f'    （无法读取：{e}）']
    for e in entries[:limit]:
        p = os.path.join(root, e)
        if os.path.isdir(p):
            n = sum(len(fs) for _, _, fs in os.walk(p))
            rows.append(f'    {e}/  （{n} 个文件）')
        else:
            rows.append(f'    {e}')
    if not entries:
        rows.append('    （空目录）')
    elif len(entries) > limit:
        rows.append(f'    … 共 {len(entries)} 项')
    return rows


PLATFORM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_ROOT = os.path.join(PLATFORM_DIR, 'data_backup')  # 不放在 public/ 下，避免被打包进 dist
BACKUP_DIR = None


def backup(out_dir, name):
    global BACKUP_DIR
    p = os.path.join(out_dir, name)
    if not os.path.exists(p):
        return
    if BACKUP_DIR is None:
        BACKUP_DIR = os.path.join(BACKUP_ROOT, time.strftime('%Y%m%d-%H%M%S'))
        os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(p, os.path.join(BACKUP_DIR, name))


def dump(obj, out_dir, name, indent=None):
    os.makedirs(out_dir, exist_ok=True)
    backup(out_dir, name)
    p = os.path.join(out_dir, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, separators=None if indent else (',', ':'))
    log(f'  -> {p} ({os.path.getsize(p) / 1024:.1f} KB)')


def deg_dist_m(lon, lat):
    return np.hypot(np.asarray(lon) - INC_LON, np.asarray(lat) - INC_LAT) * 111000


def read_points(gpd, path, radius_m):
    if not path:
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
def export_boundary(gpd, inp, out):
    p = inp.get('boundary')
    if not p:
        log('  未找到 yizhuang_boundary.shp → 保留现有 yizhuang_boundary.geojson')
        return False
    g = gpd.read_file(p).to_crs(4326)
    g['geometry'] = g.geometry.simplify(0.00005, preserve_topology=True)
    gj = json.loads(g[['geometry']].to_json())
    gj['meta'] = {'source': p}
    for i, f in enumerate(gj['features']):
        f['properties'] = {'name': '亦庄控规界' if i == 0 else f'亦庄控规界-{i}'}
    dump(gj, out, 'yizhuang_boundary.geojson')
    return True


def export_facilities(gpd, inp, out, radius_m):
    """按类别合并：找到源文件的类别用真实数据替换，其余类别保留现有 facilities.json 中的内容"""
    cur_path = os.path.join(out, 'facilities.json')
    fac = {}
    if os.path.exists(cur_path):
        with open(cur_path, encoding='utf-8') as f:
            fac = json.load(f)
    meta = fac.get('meta', {})
    sources = dict(meta.get('sources', {}))
    changed = []

    def put(key, rows, src):
        if rows is None:
            return
        if not rows:
            log(f'  ⚠️ {os.path.basename(src)} 在 {radius_m / 1000:.0f} km 范围内没有要素 → 保留现有 {key}')
            return
        fac[key] = rows
        sources[key] = src
        changed.append(key)

    fs = read_points(gpd, inp.get('fire_stations'), radius_m)
    put('fire_stations', None if fs is None else [
        {'id': f'F{i:04d}', 'name': str(r.get('name', f'消防站{i}')), 'lon': r.lon, 'lat': r.lat, 'type': 'fire_station',
         'stock': {'life_rescue': 50, 'medical': 30, 'protection': 100, 'basic': 200}}
        for i, (_, r) in enumerate(fs.iterrows())], inp.get('fire_stations'))

    hs = read_points(gpd, inp.get('hospitals'), radius_m)
    put('hospitals', None if hs is None else [
        {'id': f'H{i:04d}', 'name': str(r.get('name', f'医院{i}')), 'lon': r.lon, 'lat': r.lat, 'type': 'hospital',
         'beds': int(num(r.get(col(hs, 'bed_count') or '_'), 200)), 'level': str(r.get(col(hs, 'hospital_level') or '_', '') or '')}
        for i, (_, r) in enumerate(hs.iterrows())], inp.get('hospitals'))

    sh = read_points(gpd, inp.get('shelters'), radius_m)
    put('shelters', None if sh is None else [
        {'id': f'R{i:04d}', 'name': str(r.get('name', f'避难所{i}')), 'lon': r.lon, 'lat': r.lat, 'type': 'shelter',
         'capacity': int(num(r.get(col(sh, 'capacity') or '_'), 2000))}
        for i, (_, r) in enumerate(sh.iterrows())], inp.get('shelters'))

    sw = read_points(gpd, inp.get('subway_stations'), radius_m)
    put('subway_stations', None if sw is None else [
        {'id': f'M{i:04d}', 'name': str(r.get(col(sw, 'station_name') or '_') or r.get('name') or f'地铁站{i}'), 'lon': r.lon, 'lat': r.lat,
         'type': 'subway', 'capacity': 8000}
        for i, (_, r) in enumerate(sw.iterrows())], inp.get('subway_stations'))

    sp = inp.get('scenario_params')
    if sp:
        with open(sp, encoding='utf-8') as f:
            whs = json.load(f).get('resources', {}).get('emergency_warehouses', [])
        put('warehouses', [
            {'id': f'W{i:02d}', 'name': w['name'], 'lon': w['lon'], 'lat': w['lat'], 'type': 'warehouse',
             'assumed': '假设' in w['name'], 'stock': {'life_rescue': 200, 'medical': 100, 'protection': 500, 'basic': 1000}}
            for i, w in enumerate(whs)], sp)

    cp = inp.get('commute')
    if cp:
        df = pd.read_csv(cp, nrows=10000)
        cols = {'驾车比例': 'car_ratio', '地铁比例': 'subway_ratio', '公交比例': 'bus_ratio', '骑行比例': 'bike_ratio', '步行比例': 'walk_ratio'}
        shares = {en: float(pd.to_numeric(df[cn], errors='coerce').mean()) for cn, en in cols.items() if cn in df.columns}
        if shares.get('car_ratio') is not None:
            fac['commute_mode_shares'] = shares
            sources['commute_mode_shares'] = cp
            changed.append('commute_mode_shares')

    if not changed:
        log('  未找到任何设施源文件 → 保留现有 facilities.json')
        return False
    for key in ('fire_stations', 'warehouses', 'shelters', 'hospitals', 'subway_stations'):
        fac.setdefault(key, [])
    fac['meta'] = {**meta, 'crs': 'WGS84 (EPSG:4326)', 'radius_m': radius_m, 'sources': sources,
                   'notes': ['真实数据类别由 Step3 POI 筛选结果导出，保持原文件顺序（论文按顺序取前 N 个）；'
                             '未在 sources 中列出的类别沿用默认数据']}
    kept = [k for k in ('fire_stations', 'hospitals', 'shelters', 'subway_stations', 'warehouses', 'commute_mode_shares') if k not in changed]
    log(f'  消防站 {len(fac["fire_stations"])}，医院 {len(fac["hospitals"])}，避难所 {len(fac["shelters"])}，'
        f'地铁站 {len(fac["subway_stations"])}，仓库 {len(fac["warehouses"])}')
    log(f'  已更新：{", ".join(changed)}' + (f'；沿用默认：{", ".join(kept)}' if kept else ''))
    dump(fac, out, 'facilities.json', indent=1)
    return True


def export_population(gpd, inp, out, radius_m, cell_m):
    from shapely import contains_xy
    p = inp.get('population')
    if not p:
        log('  未找到 block_pop_study_area.shp → 保留现有 population.json')
        return False
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
    if len(pops) <= 1:
        log('  ⚠️ 裁剪范围内没有地块 → 保留现有 population.json')
        return False
    dump(out_obj, out, 'population.json')
    return True


def export_roads(inp, out, radius_m):
    p = inp.get('roads')
    if not p:
        log('  未找到 road_network_graph.gpickle → 不生成路网（引擎使用几何近似行程时间）')
        return False
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
    if not edges:
        log('  ⚠️ 裁剪范围内没有路段 → 不生成 road_network.json')
        return False
    dump(obj, out, 'road_network.json')
    return True


HELP_REGENERATE = """
  这些文件由论文数据处理脚本生成（scripts/config.py 中的原始数据路径须可访问，含外接硬盘 /Volumes/WLSSD990）：
    cd "<仓库>/1-CSTFM2026会议投稿"
    python run_all.py --only 0 2 3 4        # 研究范围、路网、POI、人口（必需）
    python run_all.py --only 5 8            # 通勤方式构成、应急仓库（可选）
  生成后重新运行本脚本即可。注意：scripts/config.py 被导入时会自动创建 output/ 下的空子目录，
  因此 output/ 存在但没有文件，通常说明该位置从未完整运行过上述步骤。
  如果当初是在另一个目录运行的，请把 --research-output 指向那里（也可以给上一级目录，脚本会自动搜索）。"""


def main():
    global BACKUP_ROOT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--research-output', required=True, help='scripts/config.py 中的 OUTPUT_DIR（或其上级目录，自动搜索）')
    ap.add_argument('--out', default=os.path.join(PLATFORM_DIR, 'public', 'data'))
    ap.add_argument('--backup-dir', default=BACKUP_ROOT, help='覆盖前备份原文件的目录')
    ap.add_argument('--radius-km', type=float, default=25, help='以太和桥为中心的裁剪半径，0=不裁剪')
    ap.add_argument('--cell-m', type=float, default=75, help='人口栅格分辨率 (m)')
    ap.add_argument('--skip-roads', action='store_true')
    ap.add_argument('--check', action='store_true', help='只检查输入文件，不写入')
    a = ap.parse_args()
    BACKUP_ROOT = os.path.abspath(a.backup_dir)
    root = os.path.abspath(os.path.expanduser(a.research_output))
    if not os.path.isdir(root):
        sys.exit(f'目录不存在：{root}')
    radius_m = a.radius_km * 1000

    log(f'输入目录：{root}')
    inp = locate_inputs(root)
    log('输入检查：')
    for k, (rel, step, raw, core) in INPUTS.items():
        p = inp.get(k)
        mark = '✅' if p else ('❌' if core else '–')
        where = os.path.relpath(p, root) if p and p.startswith(root) else (p or f'未找到（由 {step} 生成，依赖 {raw}）')
        log(f'  {mark} {rel:44s} {where}')

    core_found = [k for k, v in INPUTS.items() if v[3] and k in inp and not (k == 'roads' and a.skip_roads)]
    if not core_found:
        log('\n未找到任何核心输入文件，未写入任何数据（public/data 保持不变）。')
        log(f'{root} 的内容：')
        for row in describe_dir(root):
            log(row)
        log(HELP_REGENERATE)
        sys.exit(2)
    if a.check:
        log('\n--check 模式：不写入。去掉 --check 即可导出。')
        return

    import geopandas as gpd
    done = {}
    log('\n[1/4] 亦庄控规界'); done['yizhuang_boundary.geojson'] = export_boundary(gpd, inp, a.out)
    log('[2/4] 应急设施'); done['facilities.json'] = export_facilities(gpd, inp, a.out, radius_m)
    log('[3/4] 地块人口'); done['population.json'] = export_population(gpd, inp, a.out, radius_m, a.cell_m)
    log('[4/4] 路网')
    if a.skip_roads:
        log('  已跳过'); done['road_network.json'] = False
    else:
        done['road_network.json'] = export_roads(inp, a.out, radius_m)
    log('\n结果：')
    for f, ok in done.items():
        log(f'  {"已更新" if ok else "未改动"}  {f}')
    if BACKUP_DIR:
        log(f'原文件已备份到 {BACKUP_DIR}')
    log('重新构建（npm run build）或把 public/data/* 覆盖到已部署的 dist/data/ 即可生效（服务端需重启）。')


if __name__ == '__main__':
    main()
