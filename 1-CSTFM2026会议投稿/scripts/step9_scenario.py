"""
Step 9: 事故场景构建
===================
功能：
  1. 高斯烟羽模型模拟危险气体扩散
  2. 危险区域划分（核心区 / 警戒区 / 影响区）
  3. 受影响人口估算（分时段、分人群类型）
  4. 受影响设施统计
  5. 道路封闭与拥堵模拟
  6. 输出场景 JSON + 大量可视化

前置条件：step0 ~ step8 全部完成
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import json
import pickle
import warnings
warnings.filterwarnings('ignore')
from config import *

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


# ==================== 高斯烟羽模型 ====================

def gaussian_plume(x, y, Q, u, H, sigma_y, sigma_z):
    """
    高斯烟羽模型计算某点(x,y)的气体浓度 (mg/m³)
    x, y: 相对于泄漏源的下风向距离和横风向距离 (m)
    Q: 排放速率 (mg/s)
    u: 风速 (m/s)
    H: 有效排放高度 (m)
    sigma_y, sigma_z: 扩散参数 (m)
    """
    if x <= 0:
        return 0.0
    C = (Q / (2 * np.pi * u * sigma_y * sigma_z)) * \
        np.exp(-0.5 * (y / sigma_y) ** 2) * \
        (np.exp(-0.5 * ((0 - H) / sigma_z) ** 2) +
         np.exp(-0.5 * ((0 + H) / sigma_z) ** 2))
    return max(C, 0)


def pasquill_sigma(x_m, stability='D'):
    """
    Pasquill-Gifford 扩散参数
    stability: A(极不稳定) ~ F(极稳定)，城市默认 D(中性)
    """
    # 简化的经验公式 (Briggs, 1973, 城市条件)
    params = {
        'A': (0.32, 0.0004, 0.24, 0.001),
        'B': (0.22, 0.0004, 0.16, 0.001),
        'C': (0.16, 0.0004, 0.11, 0.001),
        'D': (0.11, 0.0004, 0.08, 0.0015),
        'E': (0.08, 0.0004, 0.06, 0.003),
        'F': (0.06, 0.0004, 0.04, 0.003),
    }
    a, b, c, d = params.get(stability, params['D'])
    sigma_y = a * x_m / np.sqrt(1 + b * x_m)
    sigma_z = c * x_m / np.sqrt(1 + d * x_m)
    return max(sigma_y, 0.1), max(sigma_z, 0.1)


def compute_plume_grid(incident_lon, incident_lat, params, grid_size=100, extent_m=5000):
    """
    在事故点周围计算网格化的浓度场
    返回: lons, lats, concentrations (2D arrays), 以及风向信息
    """
    Q = params['leak_rate_kg_per_min'] * 1e6 / 60  # mg/s
    u = max(params['wind_speed_m_s'], 0.5)
    H = params.get('release_height_m', 2.0)
    wind_dir_deg = params['wind_direction_deg']  # 风来的方向（气象约定）
    stability = params.get('stability_class', 'D')

    # 风来的方向 → 气体飘的方向（加180度）
    plume_dir_rad = np.radians((wind_dir_deg + 180) % 360)

    # 创建网格 (相对于事故点的米制偏移)
    n = int(2 * extent_m / grid_size) + 1
    xs = np.linspace(-extent_m, extent_m, n)
    ys = np.linspace(-extent_m, extent_m, n)
    XX, YY = np.meshgrid(xs, ys)

    # 旋转到风向坐标系：x轴 = 下风向，y轴 = 横风向
    cos_a = np.cos(plume_dir_rad)
    sin_a = np.sin(plume_dir_rad)
    # 网格点在东(E)-北(N)坐标系，转到下风向坐标
    X_wind = XX * sin_a + YY * cos_a   # 下风向距离
    Y_wind = XX * cos_a - YY * sin_a   # 横风向距离

    # 计算浓度
    conc = np.zeros_like(XX)
    for i in range(n):
        for j in range(n):
            xw = X_wind[i, j]
            yw = Y_wind[i, j]
            if xw > 10:  # 仅下风向有意义
                sy, sz = pasquill_sigma(xw, stability)
                conc[i, j] = gaussian_plume(xw, yw, Q, u, H, sy, sz)

    # 转换网格坐标为经纬度
    deg_per_m_lon = 1.0 / (111320 * np.cos(np.radians(incident_lat)))
    deg_per_m_lat = 1.0 / 110540
    lons = incident_lon + XX * deg_per_m_lon
    lats = incident_lat + YY * deg_per_m_lat

    return lons, lats, conc, plume_dir_rad


def extract_contour_polygon(lons, lats, conc, threshold, incident_lon, incident_lat):
    """从浓度场提取等值线多边形"""
    try:
        fig_tmp, ax_tmp = plt.subplots()
        cs = ax_tmp.contour(lons, lats, conc, levels=[threshold])
        plt.close(fig_tmp)
        polygons = []
        for path in cs.collections[0].get_paths():
            coords = path.vertices
            if len(coords) >= 3:
                polygons.append(Polygon(coords))
        if polygons:
            return unary_union(polygons)
    except Exception:
        pass
    # 回退：用圆形
    return Point(incident_lon, incident_lat).buffer(0.01)


def main():
    print("=" * 60)
    print("Step 9: 事故场景构建")
    print("=" * 60)

    out_dir = DIRS['scenario']
    fig_dir = DIRS['figures']

    # ------------------------------------------------------------------
    # 1. 加载场景参数
    # ------------------------------------------------------------------
    print("\n[1/6] 加载场景参数...")
    param_path = os.path.join(DIRS['integrated'], "scenario_params.json")
    with open(param_path, 'r', encoding='utf-8') as f:
        scenario = json.load(f)

    inc = scenario['incident']
    print(f"  事故位置: ({inc['location']['lon']}, {inc['location']['lat']})")
    print(f"  泄漏气体: {inc['gas_type']}")
    print(f"  泄漏速率: {inc['leak_rate_kg_per_min']} kg/min")
    print(f"  风速: {inc['wind_speed_m_s']} m/s")
    print(f"  风向: {inc['wind_direction_deg']}° (气象学，风从此方向来)")

    # 氯气毒性阈值 (mg/m³)
    gas_thresholds = {
        '氯气': {
            'IDLH': 29.0,          # 立即危害生命和健康 (ppm≈10, mg/m³≈29)
            'ERPG3': 20.0,         # 可能致命
            'ERPG2': 3.0,          # 可能导致严重健康影响
            'ERPG1': 1.0,          # 可能引起轻微不适
            'detection': 0.5,      # 可嗅到
        },
        '氨气': {
            'IDLH': 210.0,
            'ERPG3': 750.0,
            'ERPG2': 150.0,
            'ERPG1': 25.0,
            'detection': 5.0,
        }
    }
    thresholds = gas_thresholds.get(inc['gas_type'], gas_thresholds['氯气'])
    print(f"\n  {inc['gas_type']}毒性阈值 (mg/m³):")
    for k, v in thresholds.items():
        print(f"    {k}: {v}")

    # ------------------------------------------------------------------
    # 2. 高斯烟羽扩散模拟
    # ------------------------------------------------------------------
    print("\n[2/6] 高斯烟羽扩散模拟...")
    plume_params = {
        'leak_rate_kg_per_min': inc['leak_rate_kg_per_min'],
        'wind_speed_m_s': inc['wind_speed_m_s'],
        'wind_direction_deg': inc['wind_direction_deg'],
        'release_height_m': 2.0,
        'stability_class': 'D',
    }
    lons, lats, conc, plume_dir = compute_plume_grid(
        inc['location']['lon'], inc['location']['lat'],
        plume_params, grid_size=50, extent_m=6000
    )
    print(f"  浓度场网格: {conc.shape}")
    print(f"  最大浓度: {conc.max():.2f} mg/m³")
    print(f"  烟羽方向: {np.degrees(plume_dir):.0f}° (从北顺时针)")

    # ------------------------------------------------------------------
    # 3. 危险区域划分
    # ------------------------------------------------------------------
    print("\n[3/6] 危险区域划分...")
    zone_thresholds = {
        'core_danger':   thresholds['ERPG3'],   # 核心危险区
        'warning':       thresholds['ERPG2'],    # 警戒区
        'influence':     thresholds['ERPG1'],    # 影响区
    }

    zones = {}
    inc_lon, inc_lat = inc['location']['lon'], inc['location']['lat']

    for zone_name, threshold in zone_thresholds.items():
        poly = extract_contour_polygon(lons, lats, conc, threshold, inc_lon, inc_lat)
        zones[zone_name] = poly
        area_km2 = gpd.GeoDataFrame(geometry=[poly], crs=WGS84_CRS).to_crs(UTM_CRS).geometry.area.values[0] / 1e6
        print(f"  {zone_name} (>{threshold} mg/m³): {area_km2:.2f} km²")

    # 同时生成基于距离的圆形区域（用于道路封闭判定）
    inc_gdf = gpd.GeoDataFrame(geometry=[Point(inc_lon, inc_lat)], crs=WGS84_CRS)
    inc_proj = inc_gdf.to_crs(UTM_CRS)
    distance_zones = {}
    for name, radius_m in [('closure_500m', 500), ('closure_1km', 1000),
                            ('congestion_3km', 3000), ('influence_5km', 5000)]:
        circle_proj = inc_proj.geometry.buffer(radius_m)
        circle_wgs = gpd.GeoDataFrame(geometry=circle_proj, crs=UTM_CRS).to_crs(WGS84_CRS)
        distance_zones[name] = circle_wgs.geometry.values[0]

    # 保存区域
    zone_records = []
    for name, poly in {**zones, **distance_zones}.items():
        zone_records.append({'zone': name, 'geometry': poly})
    zones_gdf = gpd.GeoDataFrame(zone_records, crs=WGS84_CRS)
    zones_gdf.to_file(os.path.join(out_dir, "danger_zones.shp"), encoding='utf-8')

    # ------------------------------------------------------------------
    # 4. 受影响人口估算
    # ------------------------------------------------------------------
    print("\n[4/6] 受影响人口估算...")
    pop_path = os.path.join(DIRS['population'], "block_pop_study_area.shp")
    block_pop = gpd.read_file(pop_path)

    # 找人口字段
    num_cols = block_pop.select_dtypes(include=[np.number]).columns.tolist()
    pop_col = None
    for c in ['pop', 'population', 'POP', 'POPULATION', 'total', 'Total', 'count', 'value']:
        if c in num_cols:
            pop_col = c
            break
    if pop_col is None and num_cols:
        pop_col = num_cols[0]

    pop_results = {}
    if pop_col:
        for zone_name, poly in {**zones, **distance_zones}.items():
            try:
                affected = gpd.clip(block_pop, poly)
                total_pop = affected[pop_col].sum()
                pop_results[zone_name] = {
                    'total': float(total_pop),
                    'blocks': len(affected),
                }
                # 分人群类型
                if 'pop_children' in affected.columns:
                    pop_results[zone_name]['children'] = float(affected['pop_children'].sum())
                if 'pop_elderly' in affected.columns:
                    pop_results[zone_name]['elderly'] = float(affected['pop_elderly'].sum())
                if 'pop_working' in affected.columns:
                    pop_results[zone_name]['working_age'] = float(affected['pop_working'].sum())
                print(f"  {zone_name}: {total_pop:,.0f} 人 ({len(affected)} 地块)")
            except Exception as e:
                print(f"  ⚠️ {zone_name} 裁剪失败: {e}")
                pop_results[zone_name] = {'total': 0, 'blocks': 0}

    # ------------------------------------------------------------------
    # 5. 受影响设施统计
    # ------------------------------------------------------------------
    print("\n[5/6] 受影响设施统计...")
    facility_impacts = {}

    for fac_name, fac_file in [('hospitals', 'hospitals.shp'), ('fire_stations', 'fire_stations.shp'),
                                 ('shelters', 'shelters.shp'), ('subway_stations', 'subway_stations.shp')]:
        fac_path = os.path.join(DIRS['poi'], fac_file)
        if not os.path.exists(fac_path):
            continue
        fac = gpd.read_file(fac_path)
        facility_impacts[fac_name] = {}

        for zone_name, poly in distance_zones.items():
            try:
                in_zone = gpd.clip(fac, poly)
                facility_impacts[fac_name][zone_name] = {
                    'count': len(in_zone),
                    'names': in_zone['name'].tolist()[:10] if 'name' in in_zone.columns else []
                }
            except Exception:
                facility_impacts[fac_name][zone_name] = {'count': 0, 'names': []}

        print(f"  {fac_name}:")
        for zn in ['closure_1km', 'congestion_3km', 'influence_5km']:
            cnt = facility_impacts[fac_name].get(zn, {}).get('count', 0)
            print(f"    {zn}: {cnt}")

    # ------------------------------------------------------------------
    # 6. 道路影响分析
    # ------------------------------------------------------------------
    print("\n[5.5/6] 道路影响分析...")
    road_path = os.path.join(DIRS['road_network'], "roads_study_area.shp")
    roads = gpd.read_file(road_path)

    road_impacts = {}
    for zone_name, poly in distance_zones.items():
        try:
            affected_roads = gpd.clip(roads, poly)
            total_km = affected_roads['length_m'].sum() / 1000 if 'length_m' in affected_roads.columns else 0
            road_impacts[zone_name] = {
                'road_count': len(affected_roads),
                'total_km': float(total_km),
            }
            # 按道路等级统计
            if 'fclass' in affected_roads.columns:
                by_class = affected_roads.groupby('fclass')['length_m'].sum() / 1000
                road_impacts[zone_name]['by_class'] = by_class.to_dict()
            print(f"  {zone_name}: {len(affected_roads)} 条道路, {total_km:.1f} km")
        except Exception:
            road_impacts[zone_name] = {'road_count': 0, 'total_km': 0}

    # ------------------------------------------------------------------
    # 保存结果 JSON
    # ------------------------------------------------------------------
    results = {
        'incident': inc,
        'plume_params': plume_params,
        'gas_thresholds': thresholds,
        'zone_thresholds': {k: float(v) for k, v in zone_thresholds.items()},
        'affected_population': pop_results,
        'facility_impacts': facility_impacts,
        'road_impacts': road_impacts,
        'max_concentration_mg_m3': float(conc.max()),
    }
    json_path = os.path.join(out_dir, "scenario_results.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  ✅ 场景结果 JSON: {json_path}")

    # 保存浓度场数据
    np.savez(os.path.join(out_dir, "plume_concentration.npz"),
             lons=lons, lats=lats, conc=conc)

    # ------------------------------------------------------------------
    # 可视化
    # ------------------------------------------------------------------
    print("\n[6/6] 生成可视化...")
    plot_scenario(lons, lats, conc, zones, distance_zones, plume_dir,
                  pop_results, facility_impacts, road_impacts,
                  thresholds, inc, plume_params, fig_dir, out_dir)

    print("\n" + "=" * 60)
    print("Step 9 完成")
    print("=" * 60)


def plot_scenario(lons, lats, conc, zones, distance_zones, plume_dir,
                  pop_results, facility_impacts, road_impacts,
                  thresholds, inc, plume_params, fig_dir, out_dir):
    """生成多张场景可视化图"""

    # 加载底图
    study_area = gpd.read_file(os.path.join(DIRS['study_area'], "study_area_buffer.shp"))
    core = gpd.read_file(os.path.join(DIRS['study_area'], "yizhuang_boundary.shp"))
    roads = gpd.read_file(os.path.join(DIRS['road_network'], "roads_study_area.shp"))
    incident = gpd.read_file(os.path.join(DIRS['study_area'], "incident_point.shp"))
    hospitals = gpd.read_file(os.path.join(DIRS['poi'], "hospitals.shp"))
    fire_stations = gpd.read_file(os.path.join(DIRS['poi'], "fire_stations.shp"))
    shelters = gpd.read_file(os.path.join(DIRS['poi'], "shelters.shp"))

    inc_lon, inc_lat = inc['location']['lon'], inc['location']['lat']
    pad = 0.06  # 显示范围

    # ========== 图1：气体扩散浓度场 ==========
    fig1, ax1 = plt.subplots(figsize=(14, 12))
    roads.plot(ax=ax1, color='#E0E0E0', linewidth=0.2)
    core.boundary.plot(ax=ax1, color='#E65100', linewidth=1.5)

    # 浓度等值面
    conc_masked = np.ma.masked_where(conc < 0.01, conc)
    levels = [0.01, 0.1, 0.5, 1.0, 3.0, 10.0, 20.0, 50.0]
    cmap = plt.cm.YlOrRd
    cf = ax1.contourf(lons, lats, conc_masked, levels=levels, cmap=cmap,
                       alpha=0.6, extend='max')
    plt.colorbar(cf, ax=ax1, label=f'{inc["gas_type"]}浓度 (mg/m³)', shrink=0.7)

    # 等值线
    cs = ax1.contour(lons, lats, conc, levels=[thresholds['ERPG1'], thresholds['ERPG2'], thresholds['ERPG3']],
                      colors=['#FFC107', '#FF5722', '#B71C1C'], linewidths=[1, 1.5, 2])
    ax1.clabel(cs, inline=True, fontsize=8, fmt='%.1f')

    # 风向箭头
    arrow_len = 0.03
    dx = arrow_len * np.sin(plume_dir)
    dy = arrow_len * np.cos(plume_dir)
    ax1.annotate('', xy=(inc_lon + dx, inc_lat + dy),
                xytext=(inc_lon, inc_lat),
                arrowprops=dict(arrowstyle='->', color='blue', lw=2.5))
    ax1.text(inc_lon + dx * 1.3, inc_lat + dy * 1.3, f'风向\n{inc["wind_speed_m_s"]}m/s',
            fontsize=9, color='blue', ha='center', fontweight='bold')

    incident.plot(ax=ax1, color='red', marker='*', markersize=300, zorder=10)
    ax1.set_xlim(inc_lon - pad, inc_lon + pad)
    ax1.set_ylim(inc_lat - pad, inc_lat + pad)
    ax1.set_title(f'高斯烟羽扩散模拟 — {inc["gas_type"]}泄漏\n'
                  f'泄漏速率: {inc["leak_rate_kg_per_min"]} kg/min, '
                  f'风速: {inc["wind_speed_m_s"]} m/s, 稳定度: D',
                  fontsize=14, fontweight='bold')
    ax1.set_xlabel('经度 (°E)')
    ax1.set_ylabel('纬度 (°N)')
    ax1.grid(True, alpha=0.2)

    legend_items = [
        Line2D([0],[0], color='#FFC107', linewidth=1, label=f'ERPG-1 ({thresholds["ERPG1"]} mg/m³)'),
        Line2D([0],[0], color='#FF5722', linewidth=1.5, label=f'ERPG-2 ({thresholds["ERPG2"]} mg/m³)'),
        Line2D([0],[0], color='#B71C1C', linewidth=2, label=f'ERPG-3 ({thresholds["ERPG3"]} mg/m³)'),
        Line2D([0],[0], marker='*', color='red', linestyle='None', markersize=12, label='泄漏源'),
    ]
    ax1.legend(handles=legend_items, loc='upper left', fontsize=9, framealpha=0.9)

    fig1_path = os.path.join(fig_dir, "step9_plume_dispersion.png")
    fig1.savefig(fig1_path, dpi=150, bbox_inches='tight')
    plt.close(fig1)
    print(f"  ✅ 图1 气体扩散: {fig1_path}")

    # ========== 图2：危险区域与设施 ==========
    fig2, ax2 = plt.subplots(figsize=(14, 12))
    roads.plot(ax=ax2, color='#E0E0E0', linewidth=0.2)
    core.boundary.plot(ax=ax2, color='#E65100', linewidth=1.5)

    # 绘制距离圈
    zone_styles = {
        'closure_500m':   ('#B71C1C', 0.3, '500m 封闭区'),
        'closure_1km':    ('#E53935', 0.2, '1km 核心封闭'),
        'congestion_3km': ('#FF9800', 0.1, '3km 拥堵区'),
        'influence_5km':  ('#FFC107', 0.05, '5km 影响区'),
    }
    for zname in ['influence_5km', 'congestion_3km', 'closure_1km', 'closure_500m']:
        poly = distance_zones[zname]
        color, alpha, label = zone_styles[zname]
        gpd.GeoDataFrame(geometry=[poly], crs=WGS84_CRS).plot(
            ax=ax2, color=color, alpha=alpha, edgecolor=color, linewidth=1.5)

    # 设施
    shelters.plot(ax=ax2, color='#4CAF50', marker='s', markersize=8, alpha=0.4, zorder=6)
    hospitals.plot(ax=ax2, color='#D32F2F', marker='P', markersize=25, zorder=8,
                   edgecolor='white', linewidth=0.3)
    fire_stations.plot(ax=ax2, color='#FF6F00', marker='^', markersize=40, zorder=9,
                       edgecolor='white', linewidth=0.3)
    incident.plot(ax=ax2, color='red', marker='*', markersize=300, zorder=10)

    ax2.set_xlim(inc_lon - pad, inc_lon + pad)
    ax2.set_ylim(inc_lat - pad, inc_lat + pad)
    ax2.set_title('危险区域划分与应急设施分布', fontsize=14, fontweight='bold')
    ax2.set_xlabel('经度 (°E)')
    ax2.set_ylabel('纬度 (°N)')
    ax2.grid(True, alpha=0.2)

    legend_items2 = [
        plt.Rectangle((0,0),1,1, fc='#B71C1C', alpha=0.3, label='500m 封闭区'),
        plt.Rectangle((0,0),1,1, fc='#E53935', alpha=0.2, label='1km 核心封闭'),
        plt.Rectangle((0,0),1,1, fc='#FF9800', alpha=0.1, label='3km 拥堵区'),
        plt.Rectangle((0,0),1,1, fc='#FFC107', alpha=0.05, label='5km 影响区'),
        Line2D([0],[0], marker='P', color='#D32F2F', linestyle='None', markersize=8, label='医院'),
        Line2D([0],[0], marker='^', color='#FF6F00', linestyle='None', markersize=8, label='消防站'),
        Line2D([0],[0], marker='s', color='#4CAF50', linestyle='None', markersize=6, label='避难场所'),
        Line2D([0],[0], marker='*', color='red', linestyle='None', markersize=12, label='事故点'),
    ]
    ax2.legend(handles=legend_items2, loc='upper left', fontsize=9, framealpha=0.9)

    fig2_path = os.path.join(fig_dir, "step9_danger_zones.png")
    fig2.savefig(fig2_path, dpi=150, bbox_inches='tight')
    plt.close(fig2)
    print(f"  ✅ 图2 危险区域: {fig2_path}")

    # ========== 图3：受影响人口统计 ==========
    fig3, axes3 = plt.subplots(1, 3, figsize=(20, 7))

    # 3a: 各区域总人口
    ax3a = axes3[0]
    zone_names_ordered = ['closure_500m', 'closure_1km', 'congestion_3km', 'influence_5km']
    zone_labels = ['500m\n封闭区', '1km\n核心区', '3km\n拥堵区', '5km\n影响区']
    zone_pops = [pop_results.get(z, {}).get('total', 0) for z in zone_names_ordered]
    colors_bar = ['#B71C1C', '#E53935', '#FF9800', '#FFC107']
    bars = ax3a.bar(zone_labels, zone_pops, color=colors_bar, edgecolor='white')
    for bar, val in zip(bars, zone_pops):
        ax3a.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                 f'{val:,.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    ax3a.set_ylabel('人口数')
    ax3a.set_title('各危险区域受影响人口', fontsize=13, fontweight='bold')

    # 3b: 1km区域人口结构
    ax3b = axes3[1]
    km1_pop = pop_results.get('closure_1km', {})
    if km1_pop.get('children', 0) > 0:
        pop_types = ['儿童(0-14)', '老人(60+)', '劳动力(15-59)']
        pop_vals = [km1_pop.get('children', 0), km1_pop.get('elderly', 0), km1_pop.get('working_age', 0)]
        pop_colors = ['#42A5F5', '#EF5350', '#66BB6A']
        wedges, texts, autotexts = ax3b.pie(pop_vals, labels=pop_types, colors=pop_colors,
                                             autopct='%1.1f%%', pctdistance=0.8)
        ax3b.set_title(f'1km核心区人口结构\n(共{km1_pop.get("total",0):,.0f}人)',
                      fontsize=13, fontweight='bold')
    else:
        ax3b.text(0.5, 0.5, '无年龄结构数据', ha='center', va='center', fontsize=12)
        ax3b.set_title('1km核心区人口结构', fontsize=13, fontweight='bold')

    # 3c: 受影响设施统计
    ax3c = axes3[2]
    fac_types = []
    fac_counts_1km = []
    fac_counts_5km = []
    for fac_name, fac_label in [('hospitals', '医院'), ('fire_stations', '消防站'),
                                  ('shelters', '避难所'), ('subway_stations', '地铁站')]:
        if fac_name in facility_impacts:
            fac_types.append(fac_label)
            fac_counts_1km.append(facility_impacts[fac_name].get('closure_1km', {}).get('count', 0))
            fac_counts_5km.append(facility_impacts[fac_name].get('influence_5km', {}).get('count', 0))
    x = np.arange(len(fac_types))
    w = 0.35
    ax3c.bar(x - w/2, fac_counts_1km, w, color='#E53935', alpha=0.8, label='1km 核心区')
    ax3c.bar(x + w/2, fac_counts_5km, w, color='#FFC107', alpha=0.8, label='5km 影响区')
    ax3c.set_xticks(x)
    ax3c.set_xticklabels(fac_types)
    ax3c.set_ylabel('设施数量')
    ax3c.set_title('各区域受影响设施', fontsize=13, fontweight='bold')
    ax3c.legend()

    fig3.suptitle('Step 9: 事故影响评估', fontsize=16, fontweight='bold')
    fig3_path = os.path.join(fig_dir, "step9_impact_assessment.png")
    fig3.savefig(fig3_path, dpi=150, bbox_inches='tight')
    plt.close(fig3)
    print(f"  ✅ 图3 影响评估: {fig3_path}")

    # ========== 图4：多时段对比（风向敏感性） ==========
    fig4, axes4 = plt.subplots(2, 2, figsize=(18, 16))
    wind_scenarios = [
        ('西南风 (225°)', 225, 3.0),
        ('北风 (0°)', 0, 3.0),
        ('东风 (90°)', 90, 3.0),
        ('强西南风 (225°)', 225, 8.0),
    ]
    for ax_idx, (title, wind_dir, wind_spd) in enumerate(wind_scenarios):
        ax = axes4[ax_idx // 2][ax_idx % 2]
        roads.plot(ax=ax, color='#E0E0E0', linewidth=0.15)

        params_var = plume_params.copy()
        params_var['wind_direction_deg'] = wind_dir
        params_var['wind_speed_m_s'] = wind_spd
        l, la, c, pd_var = compute_plume_grid(inc_lon, inc_lat, params_var, grid_size=80, extent_m=5000)
        c_masked = np.ma.masked_where(c < 0.1, c)
        ax.contourf(l, la, c_masked, levels=[0.1, 1, 3, 10, 20, 50], cmap='YlOrRd', alpha=0.5)
        ax.contour(l, la, c, levels=[thresholds['ERPG2']], colors=['red'], linewidths=1.5)
        incident.plot(ax=ax, color='red', marker='*', markersize=200, zorder=10)
        ax.set_xlim(inc_lon - pad, inc_lon + pad)
        ax.set_ylim(inc_lat - pad, inc_lat + pad)
        ax.set_title(f'{title}, 风速 {wind_spd} m/s', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.2)

    fig4.suptitle('风向/风速敏感性分析（红线 = ERPG-2 警戒阈值）', fontsize=16, fontweight='bold')
    fig4_path = os.path.join(fig_dir, "step9_wind_sensitivity.png")
    fig4.savefig(fig4_path, dpi=150, bbox_inches='tight')
    plt.close(fig4)
    print(f"  ✅ 图4 风向敏感性: {fig4_path}")


if __name__ == '__main__':
    main()
