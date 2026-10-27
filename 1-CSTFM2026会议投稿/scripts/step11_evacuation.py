"""
Step 11: 多类型人员救援疏散优化（ERPG 分区版）
================================================
核心改进（相对 V1）：
  ✅ 1. 使用 ERPG 扇形区域（而非 3km 圆形）统计受影响人口
  ✅ 2. 分区差异化疏散策略：
        - ERPG-3: 全部人群(k=1,2,3)强制疏散
        - ERPG-2: k=1,k=2 疏散；k=3 就地避难
        - ERPG-1: k=1 疏散；k=2,k=3 就地避难
  ✅ 3. 就地避难人口产生物资配送需求（输出给 step10）
  ✅ 4. 疏散起点按 ERPG 区域生成（20-30 个）
  ✅ 5. 为 k=3 预留部分大容量运力（弹性优先级）
  ✅ 6. 路网 Dijkstra 行程时间 + 通勤 OD 数据融合

前置条件：step0 ~ step10
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import Point
from shapely.ops import unary_union
import json
import copy
import warnings
warnings.filterwarnings('ignore')
from config import *

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ==================== 人群分类 ====================
POP_CLASSES = {
    1: {'name': '重伤/中毒者',   'name_en': 'Critical',   'weight': 10,
        'dest': 'hospital',
        'color': '#B71C1C',
        'allowed_modes': ['ambulance', 'helicopter']},
    2: {'name': '老人/儿童/残障', 'name_en': 'Vulnerable', 'weight': 5,
        'dest': 'hospital_or_shelter',
        'color': '#FF6F00',
        'allowed_modes': ['ambulance', 'helicopter', 'bus', 'car', 'subway']},
    3: {'name': '一般健康人员',   'name_en': 'General',    'weight': 1,
        'dest': 'shelter',
        'color': '#1976D2',
        'allowed_modes': ['bus', 'car', 'subway']},
}

# ==================== 交通工具 ====================
VEHICLE_MODES_DEFAULT = {
    'ambulance':  {'name': '救护车', 'capacity': 3,   'speed_kmh': 50,  'count': 15,
                   'color': '#D32F2F', 'serves': [1, 2]},
    'helicopter': {'name': '直升机', 'capacity': 6,   'speed_kmh': 150, 'count': 3,
                   'color': '#7B1FA2', 'serves': [1, 2]},
    'bus':        {'name': '公交车', 'capacity': 50,  'speed_kmh': 30,  'count': 20,
                   'color': '#2E7D32', 'serves': [2, 3]},
    'car':        {'name': '私家车', 'capacity': 4,   'speed_kmh': 35,  'count': 100,
                   'color': '#455A64', 'serves': [2, 3]},
    'subway':     {'name': '地铁',   'capacity': 1200, 'speed_kmh': 40,  'count': 15,
                   'color': '#0D47A1', 'serves': [2, 3]},
}

# 目标函数权重
Z1_WEIGHT = 1.0
Z2_WEIGHT = 0.01
Z3_WEIGHT = 100.0
P_UNSAT = 500

# ==================== ERPG 分区疏散规则 ====================
# 每个 ERPG 区域中，哪些 k 类人群需要疏散
EVAC_RULES = {
    'erpg3': {1: True,  2: True,  3: True},   # 全部疏散
    'erpg2': {1: True,  2: True,  3: False},   # k=3 就地避难
    'erpg1': {1: True,  2: False, 3: False},   # 仅 k=1 疏散
}

# 弹性优先级：每个时间步中，为 k=3 预留的大容量运力比例
K3_RESERVED_RATIO = 0.25  # 25% 的公交和地铁运力预留给 k=3


class EvacNode:
    """疏散网络节点"""
    def __init__(self, nid, name, lon, lat, ntype, **attrs):
        self.id = nid
        self.name = name
        self.lon = lon
        self.lat = lat
        self.type = ntype
        self.attrs = attrs
        self.population = {1: 0, 2: 0, 3: 0}
        self.erpg_zone = attrs.get('erpg_zone', None)  # 所属 ERPG 区域
        self.capacity = attrs.get('capacity', float('inf'))
        self._initial_capacity = attrs.get('capacity', float('inf'))

    def reset_capacity(self):
        self.capacity = self._initial_capacity

    def euclidean_m(self, other):
        dlat = (other.lat - self.lat) * 110540
        dlon = (other.lon - self.lon) * 111320 * np.cos(np.radians(self.lat))
        return np.sqrt(dlat**2 + dlon**2)


# ==================== 路网 ====================

def load_router(incident_mode=True):
    from network_router import NetworkRouter
    graph_path = os.path.join(DIRS['road_network'], "road_network_graph.gpickle")
    if not os.path.exists(graph_path):
        print("  ⚠️ 路网图不存在，将使用欧氏距离兜底")
        return None
    return NetworkRouter(
        graph_path, incident_mode=incident_mode,
        incident_lon=INCIDENT_LON, incident_lat=INCIDENT_LAT,
        closure_radius_m=1000, congestion_radius_m=3000,
    )


def get_travel_time_min(router, node_a, node_b, speed_kmh):
    if router is not None:
        return router.travel_time_min(node_a.lon, node_a.lat,
                                       node_b.lon, node_b.lat)
    else:
        dist_m = node_a.euclidean_m(node_b)
        return (dist_m / 1000) / speed_kmh * 60


# ==================== 通勤数据 ====================

def load_commute_mode_share():
    commute_path = os.path.join(DIRS['commute'], "commute_study_area.csv")
    if not os.path.exists(commute_path):
        print("  ⚠️ 通勤数据不存在，使用默认方式构成")
        return {'car_ratio': 0.30, 'subway_ratio': 0.25, 'bus_ratio': 0.20}
    try:
        df = pd.read_csv(commute_path, nrows=10000)
        mode_cols = {'驾车比例': 'car_ratio', '地铁比例': 'subway_ratio',
                     '公交比例': 'bus_ratio', '骑行比例': 'bike_ratio',
                     '步行比例': 'walk_ratio'}
        result = {}
        for cn_col, en_key in mode_cols.items():
            if cn_col in df.columns:
                val = pd.to_numeric(df[cn_col], errors='coerce').mean()
                result[en_key] = float(val) if not np.isnan(val) else 0
            else:
                result[en_key] = 0
        print(f"  通勤方式构成: 驾车{result.get('car_ratio',0):.1%}, "
              f"地铁{result.get('subway_ratio',0):.1%}")
        return result
    except Exception as e:
        print(f"  ⚠️ 读取通勤数据异常: {e}")
        return {'car_ratio': 0.30, 'subway_ratio': 0.25, 'bus_ratio': 0.20}


# ==================== 基于 ERPG 区域的人口统计 ====================

def load_erpg_zone_populations():
    """
    从 step9 输出加载 ERPG 区域，与地块人口做空间裁剪。

    策略：
      1. 尝试 ERPG 等值线多边形（扇形）
      2. 如果等值线太窄导致人口=0，对每个等值线做最小缓冲（500m/1km/2km）
      3. 如果仍然为0或等值线不存在，回退到 step9 的距离圆形区域
         closure_1km → erpg3, congestion_3km → erpg2, influence_5km → erpg1

    返回: {zone_name: {'total': N, 'children': N, 'elderly': N, 'polygon': poly}}
    """
    zones_path = os.path.join(DIRS['scenario'], "danger_zones.shp")
    pop_path = os.path.join(DIRS['population'], "block_pop_study_area.shp")

    if not os.path.exists(zones_path) or not os.path.exists(pop_path):
        print("  ⚠️ danger_zones.shp 或人口数据不存在")
        return None

    zones_gdf = gpd.read_file(zones_path)
    block_pop = gpd.read_file(pop_path)

    # 确定人口字段
    pop_col = None
    for c in ['pop', 'population', 'POP', 'POPULATION', 'total', 'Total',
              'count', 'COUNT', 'value', 'num']:
        if c in block_pop.select_dtypes(include=[np.number]).columns.tolist():
            pop_col = c
            break
    if pop_col is None:
        num_cols = [c for c in block_pop.select_dtypes(include=[np.number]).columns
                    if c not in ['index_right', 'children_ratio', 'elderly_ratio',
                                 'working_age_ratio']]
        if num_cols:
            pop_col = num_cols[0]
    if pop_col is None:
        print("  ⚠️ 未找到人口字段")
        return None

    print(f"    人口字段: {pop_col}")

    # 提取所有区域多边形
    all_zones = {}
    for _, row in zones_gdf.iterrows():
        all_zones[row['zone']] = row.geometry

    def clip_population(poly):
        """裁剪人口，返回 (total, children, elderly, working)"""
        if poly is None or poly.is_empty:
            return 0, 0, 0, 0
        try:
            clipped = gpd.clip(block_pop, poly)
            total = float(clipped[pop_col].sum())
            children = float(clipped['pop_children'].sum()) if 'pop_children' in clipped.columns else total * 0.12
            elderly = float(clipped['pop_elderly'].sum()) if 'pop_elderly' in clipped.columns else total * 0.15
            working = total - children - elderly
            return total, children, elderly, working
        except Exception:
            return 0, 0, 0, 0

    # === 策略 1: 尝试 ERPG 等值线 ===
    erpg_map = {'core_danger': 'erpg3', 'warning': 'erpg2', 'influence': 'erpg1'}
    erpg_polys = {erpg_map[k]: v for k, v in all_zones.items() if k in erpg_map}

    # 环形裁剪（不重叠）
    zone_rings = {}
    if 'erpg3' in erpg_polys:
        zone_rings['erpg3'] = erpg_polys['erpg3']
    if 'erpg2' in erpg_polys:
        zone_rings['erpg2'] = (erpg_polys['erpg2'].difference(erpg_polys.get('erpg3', Point(0,0)))
                                if 'erpg3' in erpg_polys else erpg_polys['erpg2'])
    if 'erpg1' in erpg_polys:
        zone_rings['erpg1'] = (erpg_polys['erpg1'].difference(erpg_polys.get('erpg2', Point(0,0)))
                                if 'erpg2' in erpg_polys else erpg_polys['erpg1'])

    # 检查 ERPG 等值线的人口
    total_erpg_pop = 0
    for zname, poly in zone_rings.items():
        t, _, _, _ = clip_population(poly)
        total_erpg_pop += t

    if total_erpg_pop > 0:
        print("  ✅ 使用 ERPG 等值线扇形区域")
        result = {}
        for zname, poly in zone_rings.items():
            t, c, e, w = clip_population(poly)
            area_km2 = gpd.GeoDataFrame(geometry=[poly], crs=WGS84_CRS).to_crs(UTM_CRS).geometry.area.values[0] / 1e6
            result[zname] = {'total': t, 'children': c, 'elderly': e, 'working': w, 'polygon': poly}
            print(f"    {zname}: {t:,.0f} 人, 面积 {area_km2:.2f} km²")
        return result

    # === 策略 2: 缓冲 ERPG 等值线 ===
    print("  ℹ️ ERPG 等值线人口=0，尝试缓冲...")
    min_buffers = {'erpg3': 500, 'erpg2': 1500, 'erpg1': 3000}  # 最小缓冲半径(m)
    buffered_result = {}
    total_buffered_pop = 0

    for zname, poly in erpg_polys.items():
        if poly is None or poly.is_empty:
            continue
        # 对等值线做缓冲（在 UTM 投影下）
        poly_utm = gpd.GeoDataFrame(geometry=[poly], crs=WGS84_CRS).to_crs(UTM_CRS)
        buffered_utm = poly_utm.geometry.buffer(min_buffers.get(zname, 1000))
        buffered_wgs = gpd.GeoDataFrame(geometry=buffered_utm, crs=UTM_CRS).to_crs(WGS84_CRS)
        buffered_poly = buffered_wgs.geometry.values[0]

        t, c, e, w = clip_population(buffered_poly)
        total_buffered_pop += t
        buffered_result[zname] = {'total': t, 'children': c, 'elderly': e,
                                   'working': w, 'polygon': buffered_poly}

    # 环形裁剪（去重叠）
    if total_buffered_pop > 0:
        print("  ✅ 使用缓冲后的 ERPG 区域")
        # 从外到内减去，避免人口重叠计数
        if 'erpg1' in buffered_result and 'erpg2' in buffered_result:
            poly_1 = buffered_result['erpg1']['polygon']
            poly_2 = buffered_result['erpg2']['polygon']
            ring_1 = poly_1.difference(poly_2)
            t, c, e, w = clip_population(ring_1)
            buffered_result['erpg1'] = {'total': t, 'children': c, 'elderly': e,
                                         'working': w, 'polygon': ring_1}
        if 'erpg2' in buffered_result and 'erpg3' in buffered_result:
            poly_2 = buffered_result['erpg2']['polygon']
            poly_3 = buffered_result['erpg3']['polygon']
            ring_2 = poly_2.difference(poly_3)
            t, c, e, w = clip_population(ring_2)
            buffered_result['erpg2'] = {'total': t, 'children': c, 'elderly': e,
                                         'working': w, 'polygon': ring_2}

        for zname, zdata in buffered_result.items():
            area_km2 = gpd.GeoDataFrame(
                geometry=[zdata['polygon']], crs=WGS84_CRS
            ).to_crs(UTM_CRS).geometry.area.values[0] / 1e6
            print(f"    {zname}: {zdata['total']:,.0f} 人, 面积 {area_km2:.2f} km²")
        return buffered_result

    # === 策略 3: 回退到距离圆形区域 ===
    print("  ℹ️ 缓冲后仍为0，回退到距离圆形区域")
    dist_map = {
        'erpg3': 'closure_1km',
        'erpg2': 'congestion_3km',
        'erpg1': 'influence_5km',
    }
    result = {}
    for erpg_name, dist_name in dist_map.items():
        poly = all_zones.get(dist_name)
        if poly is None:
            continue
        # 环形裁剪
        if erpg_name == 'erpg2' and 'erpg3' in result:
            poly = poly.difference(result['erpg3']['polygon'])
        if erpg_name == 'erpg1' and 'erpg2' in result:
            poly = poly.difference(result['erpg2']['polygon'])

        t, c, e, w = clip_population(poly)
        area_km2 = gpd.GeoDataFrame(
            geometry=[poly], crs=WGS84_CRS
        ).to_crs(UTM_CRS).geometry.area.values[0] / 1e6
        result[erpg_name] = {'total': t, 'children': c, 'elderly': e,
                              'working': w, 'polygon': poly}
        print(f"    {erpg_name} (← {dist_name}): {t:,.0f} 人, 面积 {area_km2:.2f} km²")

    if sum(r['total'] for r in result.values()) == 0:
        print("  ⚠️ 所有区域人口均为0，请检查人口数据")
        return None

    return result


# ==================== 疏散网络构建（ERPG 版）====================

def build_evacuation_network_erpg(zone_pops, scenario_params, commute_shares):
    """
    基于 ERPG 扇形区域构建疏散网络。
    在每个 ERPG 区域内生成多个疏散起点，
    按 EVAC_RULES 确定哪些 k 类人群需要疏散。
    """
    print("  构建 ERPG 分区疏散网络...")
    inc = scenario_params['incident']['location']
    inc_point = Point(inc['lon'], inc['lat'])

    nodes = []
    nid = 0
    shelter_in_place_pop = {}  # 就地避难人口（用于物资配送）

    # 各区域的年龄结构比例
    k1_ratio = 0.02   # 重伤/中毒
    # k2 = elderly_ratio + children_ratio（从数据获取）
    # k3 = 1 - k1 - k2

    # ---- 在每个 ERPG 区域中生成疏散起点 ----
    origin_configs = {
        'erpg3': [
            ('ERPG3-北', 0, 0.004, 0.25),
            ('ERPG3-南', 0, -0.004, 0.25),
            ('ERPG3-东', 0.005, 0, 0.20),
            ('ERPG3-西', -0.005, 0, 0.20),
            ('ERPG3-中', 0, 0.001, 0.10),
        ],
        'erpg2': [
            ('ERPG2-北', 0, 0.012, 0.15),
            ('ERPG2-南', 0, -0.012, 0.15),
            ('ERPG2-东北', 0.010, 0.008, 0.12),
            ('ERPG2-东南', 0.010, -0.008, 0.12),
            ('ERPG2-西北', -0.010, 0.008, 0.12),
            ('ERPG2-西南', -0.010, -0.008, 0.12),
            ('ERPG2-东', 0.015, 0, 0.11),
            ('ERPG2-西', -0.015, 0, 0.11),
        ],
        'erpg1': [
            ('ERPG1-北', 0, 0.025, 0.12),
            ('ERPG1-南', 0, -0.025, 0.12),
            ('ERPG1-东北', 0.020, 0.018, 0.10),
            ('ERPG1-东南', 0.020, -0.018, 0.10),
            ('ERPG1-西北', -0.020, 0.018, 0.10),
            ('ERPG1-西南', -0.020, -0.018, 0.10),
            ('ERPG1-东', 0.030, 0, 0.09),
            ('ERPG1-西', -0.030, 0, 0.09),
            ('ERPG1-正北', 0, 0.035, 0.09),
            ('ERPG1-正南', 0, -0.035, 0.09),
        ],
    }

    for zone_name, configs in origin_configs.items():
        zp = zone_pops.get(zone_name, {})
        total_pop = zp.get('total', 0)
        if total_pop == 0:
            continue

        elderly_r = zp.get('elderly', 0) / max(1, total_pop)
        children_r = zp.get('children', 0) / max(1, total_pop)
        k2_ratio = elderly_r + children_r
        k3_ratio = max(0, 1 - k1_ratio - k2_ratio)

        rules = EVAC_RULES[zone_name]
        zone_shelter_pop = {1: 0, 2: 0, 3: 0}

        for name, dx, dy, share in configs:
            node = EvacNode(nid, name,
                            inc['lon'] + dx, inc['lat'] + dy,
                            'origin', erpg_zone=zone_name)
            local_pop = total_pop * share

            pop_k1 = int(local_pop * k1_ratio)
            pop_k2 = int(local_pop * k2_ratio)
            pop_k3 = int(local_pop * k3_ratio)

            # 按 EVAC_RULES 决定谁需要疏散
            node.population[1] = pop_k1 if rules[1] else 0
            node.population[2] = pop_k2 if rules[2] else 0
            node.population[3] = pop_k3 if rules[3] else 0

            # 不需要疏散的人群 → 就地避难
            if not rules[1]: zone_shelter_pop[1] += pop_k1
            if not rules[2]: zone_shelter_pop[2] += pop_k2
            if not rules[3]: zone_shelter_pop[3] += pop_k3

            nodes.append(node)
            nid += 1

        shelter_in_place_pop[zone_name] = zone_shelter_pop

    # ---- 医院 ----
    hosp_path = os.path.join(DIRS['poi'], "hospitals.shp")
    if os.path.exists(hosp_path):
        hospitals = gpd.read_file(hosp_path)
        for _, row in hospitals.iterrows():
            dist = inc_point.distance(row.geometry) * 111000
            if 2000 < dist < 12000:
                cap = int(row.get('bed_count', 200)) if 'bed_count' in row.index else 200
                nodes.append(EvacNode(nid, str(row.get('name', f'医院_{nid}')),
                                      row.geometry.x, row.geometry.y, 'hospital',
                                      capacity=cap))
                nid += 1
                if sum(1 for n in nodes if n.type == 'hospital') >= 12:
                    break

    # ---- 避难所 ----
    shelter_path = os.path.join(DIRS['poi'], "shelters.shp")
    if os.path.exists(shelter_path):
        shelters = gpd.read_file(shelter_path)
        shelters_sorted = (shelters.sort_values('capacity', ascending=False)
                           if 'capacity' in shelters.columns else shelters)
        for _, row in shelters_sorted.iterrows():
            dist = inc_point.distance(row.geometry) * 111000
            if 2000 < dist < 12000:
                cap = int(row.get('capacity', 2000)) if 'capacity' in row.index else 2000
                nodes.append(EvacNode(nid, str(row.get('name', f'避难所_{nid}')),
                                      row.geometry.x, row.geometry.y, 'shelter',
                                      capacity=cap))
                nid += 1
                if sum(1 for n in nodes if n.type == 'shelter') >= 15:
                    break

    # ---- 地铁站 ----
    sub_path = os.path.join(DIRS['poi'], "subway_stations.shp")
    if os.path.exists(sub_path):
        subs = gpd.read_file(sub_path)
        for _, row in subs.iterrows():
            dist = inc_point.distance(row.geometry) * 111000
            if 1500 < dist < 8000:
                nodes.append(EvacNode(nid, str(row.get('name', f'地铁_{nid}')),
                                      row.geometry.x, row.geometry.y, 'subway',
                                      capacity=8000))
                nid += 1
                if sum(1 for n in nodes if n.type == 'subway') >= 8:
                    break

    origins     = [n for n in nodes if n.type == 'origin']
    hospitals_n = [n for n in nodes if n.type == 'hospital']
    shelters_n  = [n for n in nodes if n.type == 'shelter']
    subways_n   = [n for n in nodes if n.type == 'subway']

    # 私家车数量调整
    car_ratio = commute_shares.get('car_ratio', 0.30)
    adjusted_car_count = max(20, int(100 * car_ratio / 0.30))

    total_evac = sum(sum(n.population.values()) for n in origins)
    total_shelter = sum(sum(v.values()) for v in shelter_in_place_pop.values())

    print(f"    疏散起点: {len(origins)} (ERPG3: {sum(1 for o in origins if o.erpg_zone=='erpg3')}, "
          f"ERPG2: {sum(1 for o in origins if o.erpg_zone=='erpg2')}, "
          f"ERPG1: {sum(1 for o in origins if o.erpg_zone=='erpg1')})")
    print(f"    医院: {len(hospitals_n)}, 避难所: {len(shelters_n)}, 地铁站: {len(subways_n)}")
    print(f"    ✅ 总待疏散人口: {total_evac:,}")
    print(f"    ✅ 就地避难人口: {total_shelter:,} (产生物资配送需求)")
    for zn in ['erpg3', 'erpg2', 'erpg1']:
        zn_origins = [o for o in origins if o.erpg_zone == zn]
        zn_pop = sum(sum(o.population.values()) for o in zn_origins)
        sp = shelter_in_place_pop.get(zn, {})
        sp_total = sum(sp.values())
        print(f"      {zn}: 疏散 {zn_pop:,}, 就地避难 {sp_total:,}")

    return (nodes, origins, hospitals_n, shelters_n, subways_n,
            adjusted_car_count, shelter_in_place_pop)


# ==================== 风险暴露计算 ====================

def compute_risk_exposure(node, conc_data, inc):
    if conc_data is None:
        dist_m = np.sqrt(
            ((node.lon - inc['lon']) * 111320 * np.cos(np.radians(node.lat)))**2 +
            ((node.lat - inc['lat']) * 110540)**2)
        return max(0, 10 - dist_m / 500)
    lons, lats, conc = conc_data['lons'], conc_data['lats'], conc_data['conc']
    lon_idx = np.argmin(np.abs(lons[0, :] - node.lon))
    lat_idx = np.argmin(np.abs(lats[:, 0] - node.lat))
    if 0 <= lat_idx < conc.shape[0] and 0 <= lon_idx < conc.shape[1]:
        return float(conc[lat_idx, lon_idx])
    return 0.0


# ==================== 疏散调度（弹性优先级版）====================

def evacuation_dispatch(origins, destinations_map, vehicle_modes,
                        router, conc_data, inc,
                        T_max=180, dt=5, flexible_priority=True):
    """
    时间步进式疏散调度（弹性优先级版）

    flexible_priority=True 时：
      - 每个时间步中，75% 的公交/地铁运力按 k=1→k=2→k=3 优先级
      - 25% 的公交/地铁运力直接分配给 k=3（若有需求）
    """
    schedule = []
    time_steps = list(range(0, T_max, dt))

    fleet = {}
    for mode_name, config in vehicle_modes.items():
        fleet[mode_name] = []
        n_vehicles = config['count']
        for i in range(n_vehicles):
            angle = 2 * np.pi * i / max(1, n_vehicles)
            offset = 0.015
            init_lon = inc['lon'] + offset * np.cos(angle)
            init_lat = inc['lat'] + offset * np.sin(angle)
            fleet[mode_name].append({
                'id': f'{mode_name}_{i}',
                'available_at': 0,
                'current_lon': init_lon,
                'current_lat': init_lat,
                'trips': 0,
                'people_moved': 0,
                'reserved_k3': False,  # 是否为 k=3 预留
            })

    # 标记 k=3 预留车辆
    if flexible_priority:
        for mode_name in ['bus', 'subway']:
            if mode_name not in fleet:
                continue
            n_reserve = max(1, int(len(fleet[mode_name]) * K3_RESERVED_RATIO))
            for i in range(n_reserve):
                fleet[mode_name][-(i+1)]['reserved_k3'] = True

    remaining = {}
    for o in origins:
        remaining[o.id] = {k: v for k, v in o.population.items()}

    timeline = []

    for t in time_steps:
        total_remaining = sum(sum(r.values()) for r in remaining.values())
        if total_remaining == 0:
            break

        risk_this_step = 0.0
        for o in origins:
            r = remaining.get(o.id, {})
            rho = compute_risk_exposure(o, conc_data, inc)
            for k, count in r.items():
                risk_this_step += POP_CLASSES[k]['weight'] * rho * count

        timeline.append({
            'time_min': t,
            'remaining': total_remaining,
            'risk_exposure': risk_this_step,
        })

        # ---- 调度：优先级 + 弹性预留 ----
        for k in [1, 2, 3]:
            allowed_modes = POP_CLASSES[k]['allowed_modes']

            origins_scored = []
            for o in origins:
                ppl = remaining[o.id].get(k, 0)
                if ppl <= 0:
                    continue
                rho = compute_risk_exposure(o, conc_data, inc)
                score = POP_CLASSES[k]['weight'] * rho * ppl
                origins_scored.append((score, -o.id, o))
            origins_scored.sort(reverse=True)

            for _, _, o in origins_scored:
                ppl = remaining[o.id].get(k, 0)
                if ppl <= 0:
                    continue

                dests = destinations_map.get(k, [])
                if not dests:
                    continue
                dests_avail = [d for d in dests if d.capacity > 0]
                if not dests_avail:
                    continue

                for mode_name in allowed_modes:
                    if mode_name not in fleet:
                        continue
                    config = vehicle_modes[mode_name]

                    for veh in fleet[mode_name]:
                        if veh['available_at'] > t:
                            continue
                        # 弹性优先级检查
                        if flexible_priority and veh['reserved_k3']:
                            if k != 3:
                                continue  # 预留车辆只服务 k=3
                        if ppl <= 0:
                            break

                        veh_node = EvacNode(-1, 'veh', veh['current_lon'],
                                            veh['current_lat'], 'temp')
                        t_to_origin = get_travel_time_min(
                            router, veh_node, o, config['speed_kmh'])

                        best_dest = None
                        best_total = float('inf')
                        for d in dests_avail:
                            if d.capacity <= 0:
                                continue
                            t_to_dest = get_travel_time_min(
                                router, o, d, config['speed_kmh'])
                            total = t_to_origin + t_to_dest
                            if total < best_total:
                                best_total = total
                                best_dest = d

                        if best_dest is None:
                            continue

                        t_od = get_travel_time_min(
                            router, o, best_dest, config['speed_kmh'])
                        arrival = t + t_to_origin + t_od
                        return_time = arrival + t_od + 2

                        batch = min(ppl, config['capacity'], int(best_dest.capacity))
                        if batch <= 0:
                            continue

                        schedule.append({
                            'time': t,
                            'arrival': float(arrival),
                            'origin': o.name,
                            'dest': best_dest.name,
                            'pop_class': k,
                            'mode': mode_name,
                            'count': batch,
                            'travel_min': float(t_od),
                            'vehicle_id': veh['id'],
                            'erpg_zone': o.erpg_zone,
                        })

                        remaining[o.id][k] = max(0, remaining[o.id][k] - batch)
                        ppl = remaining[o.id][k]
                        best_dest.capacity -= batch
                        veh['available_at'] = return_time
                        veh['current_lon'] = best_dest.lon
                        veh['current_lat'] = best_dest.lat
                        veh['trips'] += 1
                        veh['people_moved'] += batch

    total_remaining = sum(sum(r.values()) for r in remaining.values())
    timeline.append({
        'time_min': time_steps[-1] if time_steps else T_max,
        'remaining': total_remaining,
        'risk_exposure': 0,
    })

    return schedule, timeline, remaining, fleet


# ==================== 目标函数 ====================

def compute_objectives(schedule, remaining, timeline, origins):
    z1 = sum(POP_CLASSES[s['pop_class']]['weight'] * s['travel_min'] * s['count']
             for s in schedule)
    z2 = sum(t['risk_exposure'] for t in timeline)
    z3_weighted = 0
    for o in origins:
        for k in [1, 2, 3]:
            z3_weighted += P_UNSAT * POP_CLASSES[k]['weight'] * remaining[o.id].get(k, 0)
    obj = Z1_WEIGHT * z1 + Z2_WEIGHT * z2 + Z3_WEIGHT * z3_weighted
    return obj, z1, z2, z3_weighted


# ==================== 主函数 ====================

def main():
    print("=" * 60)
    print("Step 11: 多类型人员救援疏散优化（ERPG 分区版）")
    print("=" * 60)

    out_dir = DIRS['evac_opt']
    fig_dir = DIRS['figures']

    with open(os.path.join(DIRS['integrated'], "scenario_params.json"), 'r') as f:
        scenario_params = json.load(f)
    with open(os.path.join(DIRS['scenario'], "scenario_results.json"), 'r') as f:
        scenario_results = json.load(f)

    inc = scenario_params['incident']['location']

    conc_path = os.path.join(DIRS['scenario'], "plume_concentration.npz")
    conc_data = None
    if os.path.exists(conc_path):
        data = np.load(conc_path)
        conc_data = {'lons': data['lons'], 'lats': data['lats'], 'conc': data['conc']}

    # ------------------------------------------------------------------
    # 1. 加载路网 + 通勤
    # ------------------------------------------------------------------
    print("\n[1/7] 加载路网 + 通勤数据...")
    router = load_router(incident_mode=True)
    commute_shares = load_commute_mode_share()

    # ------------------------------------------------------------------
    # 2. 加载 ERPG 区域人口
    # ------------------------------------------------------------------
    print("\n[2/7] 加载 ERPG 区域人口...")
    zone_pops = load_erpg_zone_populations()

    if zone_pops is None:
        print("  ⚠️ 无法加载 ERPG 区域，请确保 step9 已运行")
        return

    # ------------------------------------------------------------------
    # 3. 构建疏散网络
    # ------------------------------------------------------------------
    print("\n[3/7] 构建 ERPG 分区疏散网络...")
    (nodes, origins, hospitals_n, shelters_n, subways_n,
     adjusted_car_count, shelter_in_place_pop) = build_evacuation_network_erpg(
        zone_pops, scenario_params, commute_shares)

    dest_map = {
        1: hospitals_n,
        2: hospitals_n + shelters_n,
        3: shelters_n + subways_n,
    }

    # ------------------------------------------------------------------
    # 4. 基准方案
    # ------------------------------------------------------------------
    print("\n[4/7] 基准方案（ERPG 分区 + 弹性优先级）...")
    modes_baseline = copy.deepcopy(VEHICLE_MODES_DEFAULT)
    modes_baseline['car']['count'] = adjusted_car_count

    def deep_copy_dest_map(dm, all_nodes):
        new_nodes = {n.id: copy.deepcopy(n) for n in all_nodes if n.type != 'origin'}
        for n in new_nodes.values():
            n.reset_capacity()
        new_map = {}
        for k, nlist in dm.items():
            new_map[k] = [new_nodes[n.id] for n in nlist if n.id in new_nodes]
        return new_map

    dest_base = deep_copy_dest_map(dest_map, nodes)
    origins_base = copy.deepcopy(origins)
    sch_base, tl_base, rem_base, fl_base = evacuation_dispatch(
        origins_base, dest_base, modes_baseline, router, conc_data, inc,
        flexible_priority=True)

    evac_base = sum(s['count'] for s in sch_base)
    rem_base_total = sum(sum(r.values()) for r in rem_base.values())
    total_pop = evac_base + rem_base_total

    print(f"  已疏散: {evac_base:,}, 未疏散: {rem_base_total:,}, "
          f"完成率: {evac_base / max(1, total_pop):.1%}")

    for k in [1, 2, 3]:
        k_sch = [s for s in sch_base if s['pop_class'] == k]
        k_evac = sum(s['count'] for s in k_sch)
        k_remain = sum(rem_base[o.id].get(k, 0) for o in origins_base)
        k_rate = k_evac / max(1, k_evac + k_remain)
        print(f"    k={k} ({POP_CLASSES[k]['name']}): 疏散 {k_evac:,}, "
              f"滞留 {k_remain:,}, 完成率 {k_rate:.1%}")

    # 分 ERPG 区域统计
    print(f"\n  分区域疏散完成率:")
    for zn in ['erpg3', 'erpg2', 'erpg1']:
        zn_sch = [s for s in sch_base if s.get('erpg_zone') == zn]
        zn_evac = sum(s['count'] for s in zn_sch)
        zn_origins = [o for o in origins_base if o.erpg_zone == zn]
        zn_remain = sum(sum(rem_base[o.id].values()) for o in zn_origins)
        zn_total = zn_evac + zn_remain
        rate = zn_evac / max(1, zn_total)
        print(f"    {zn}: {zn_evac:,}/{zn_total:,} ({rate:.1%})")

    comparison = {'baseline': {
        'label': '基准（ERPG分区+弹性优先级）',
        'evacuated': evac_base, 'remaining': rem_base_total,
        'timeline': tl_base, 'schedule': sch_base,
    }}

    # ------------------------------------------------------------------
    # 5. 对比方案
    # ------------------------------------------------------------------
    print("\n[5/7] 对比方案...")

    # 方案 B：无地铁
    print("  方案B: 无地铁...")
    modes_b = {k: copy.deepcopy(v) for k, v in VEHICLE_MODES_DEFAULT.items()
               if k != 'subway'}
    modes_b['car']['count'] = adjusted_car_count
    dest_b = {
        1: [copy.deepcopy(n) for n in hospitals_n],
        2: [copy.deepcopy(n) for n in hospitals_n] + [copy.deepcopy(n) for n in shelters_n],
        3: [copy.deepcopy(n) for n in shelters_n],
    }
    for nlist in dest_b.values():
        for n in nlist:
            n.reset_capacity()
    origins_b = copy.deepcopy(origins)
    sch_b, tl_b, rem_b, _ = evacuation_dispatch(
        origins_b, dest_b, modes_b, router, conc_data, inc, flexible_priority=True)
    evac_b = sum(s['count'] for s in sch_b)
    rem_b_total = sum(sum(r.values()) for r in rem_b.values())
    print(f"    疏散: {evac_b:,}, 完成率: {evac_b / max(1, evac_b + rem_b_total):.1%}")
    comparison['no_subway'] = {
        'label': '无地铁', 'evacuated': evac_b,
        'remaining': rem_b_total, 'timeline': tl_b, 'schedule': sch_b,
    }

    # 方案 C：无直升机
    print("  方案C: 无直升机...")
    modes_c = {k: copy.deepcopy(v) for k, v in VEHICLE_MODES_DEFAULT.items()
               if k != 'helicopter'}
    modes_c['car']['count'] = adjusted_car_count
    dest_c = deep_copy_dest_map(dest_map, nodes)
    origins_c = copy.deepcopy(origins)
    sch_c, tl_c, rem_c, _ = evacuation_dispatch(
        origins_c, dest_c, modes_c, router, conc_data, inc, flexible_priority=True)
    evac_c = sum(s['count'] for s in sch_c)
    rem_c_total = sum(sum(r.values()) for r in rem_c.values())
    print(f"    疏散: {evac_c:,}, 完成率: {evac_c / max(1, evac_c + rem_c_total):.1%}")
    comparison['no_helicopter'] = {
        'label': '无直升机', 'evacuated': evac_c,
        'remaining': rem_c_total, 'timeline': tl_c, 'schedule': sch_c,
    }

    # 方案 D：严格优先级（对照）
    print("  方案D: 严格优先级（不预留运力给k=3）...")
    modes_d = copy.deepcopy(VEHICLE_MODES_DEFAULT)
    modes_d['car']['count'] = adjusted_car_count
    dest_d = deep_copy_dest_map(dest_map, nodes)
    origins_d = copy.deepcopy(origins)
    sch_d, tl_d, rem_d, _ = evacuation_dispatch(
        origins_d, dest_d, modes_d, router, conc_data, inc,
        flexible_priority=False)  # 严格优先级
    evac_d = sum(s['count'] for s in sch_d)
    rem_d_total = sum(sum(r.values()) for r in rem_d.values())
    print(f"    疏散: {evac_d:,}, 完成率: {evac_d / max(1, evac_d + rem_d_total):.1%}")
    comparison['strict_priority'] = {
        'label': '严格优先级', 'evacuated': evac_d,
        'remaining': rem_d_total, 'timeline': tl_d, 'schedule': sch_d,
    }

    # ------------------------------------------------------------------
    # 6. 敏感性分析
    # ------------------------------------------------------------------
    print("\n[6/7] 敏感性分析...")
    sensitivity = []
    for n_amb in [5, 10, 15, 20, 30, 40, 50]:
        modes_s = copy.deepcopy(VEHICLE_MODES_DEFAULT)
        modes_s['ambulance']['count'] = n_amb
        modes_s['car']['count'] = adjusted_car_count
        dest_s = deep_copy_dest_map(dest_map, nodes)
        origins_s = copy.deepcopy(origins)
        sch_s, tl_s, rem_s, _ = evacuation_dispatch(
            origins_s, dest_s, modes_s, router, conc_data, inc, flexible_priority=True)
        k1_evac = sum(s['count'] for s in sch_s if s['pop_class'] == 1)
        k1_remain = sum(rem_s[o.id].get(1, 0) for o in origins_s)
        k1_rate = k1_evac / max(1, k1_evac + k1_remain)
        sensitivity.append({
            'n_ambulances': n_amb,
            'total_evacuated': sum(s['count'] for s in sch_s),
            'critical_evac_rate': float(k1_rate),
            'cumulative_risk': float(sum(t['risk_exposure'] for t in tl_s)),
        })
        print(f"    救护车={n_amb:2d}: k1完成率={k1_rate:.1%}")

    # ------------------------------------------------------------------
    # 7. 保存
    # ------------------------------------------------------------------
    print("\n[7/7] 保存结果...")

    # 输出就地避难人口（供 step10 使用）
    shelter_output = {
        'shelter_in_place_population': {
            zn: {str(k): v for k, v in pops.items()}
            for zn, pops in shelter_in_place_pop.items()
        },
        'evac_rules': {zn: {str(k): v for k, v in rules.items()}
                       for zn, rules in EVAC_RULES.items()},
    }

    comparison_summary = {}
    for key, res in comparison.items():
        by_class = {}
        for k in [1, 2, 3]:
            k_sch = [s for s in res['schedule'] if s['pop_class'] == k]
            k_evac = sum(s['count'] for s in k_sch)
            by_class[str(k)] = {
                'evacuated': k_evac,
                'avg_travel_min': float(np.mean([s['travel_min'] for s in k_sch])) if k_sch else 0,
            }
        by_mode = {}
        for mode in VEHICLE_MODES_DEFAULT:
            m_sch = [s for s in res['schedule'] if s['mode'] == mode]
            by_mode[mode] = {
                'trips': len(m_sch),
                'people_moved': sum(s['count'] for s in m_sch),
            }
        # 分 ERPG 区域
        by_zone = {}
        for zn in ['erpg3', 'erpg2', 'erpg1']:
            zn_sch = [s for s in res['schedule'] if s.get('erpg_zone') == zn]
            by_zone[zn] = {
                'evacuated': sum(s['count'] for s in zn_sch),
            }

        comparison_summary[key] = {
            'label': res['label'],
            'evacuated': res['evacuated'],
            'remaining': res['remaining'],
            'evac_rate': res['evacuated'] / max(1, res['evacuated'] + res['remaining']),
            'by_class': by_class,
            'by_mode': by_mode,
            'by_zone': by_zone,
            'total_risk': sum(t['risk_exposure'] for t in res['timeline']),
        }

    output = {
        'erpg_zone_populations': {
            zn: {k: v for k, v in zp.items() if k != 'polygon'}
            for zn, zp in zone_pops.items()
        },
        'evac_rules': EVAC_RULES,
        'network': {
            'origins': [{'name': n.name, 'lon': n.lon, 'lat': n.lat,
                         'pop': n.population, 'erpg_zone': n.erpg_zone}
                        for n in origins],
            'hospitals': len(hospitals_n),
            'shelters': len(shelters_n),
            'subway_stations': len(subways_n),
        },
        'pop_classes': {str(k): {kk: vv for kk, vv in v.items() if kk != 'color'}
                        for k, v in POP_CLASSES.items()},
        'vehicle_modes': {k: {kk: vv for kk, vv in v.items() if kk != 'color'}
                          for k, v in VEHICLE_MODES_DEFAULT.items()},
        'commute_mode_shares': commute_shares,
        'adjusted_car_count': adjusted_car_count,
        'shelter_in_place': shelter_output,
        'comparison': comparison_summary,
        'sensitivity_ambulance': sensitivity,
        'timelines': {k: v['timeline'] for k, v in comparison.items()},
        'uses_road_network': router is not None,
        'flexible_priority': True,
        'k3_reserved_ratio': K3_RESERVED_RATIO,
    }

    json_path = os.path.join(out_dir, "evacuation_results.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✅ JSON: {json_path}")

    print("\n" + "=" * 60)
    print("Step 11 完成（ERPG 分区版）")
    print("=" * 60)


if __name__ == '__main__':
    main()
