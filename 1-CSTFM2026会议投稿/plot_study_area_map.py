#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图1(a): 六环路太和桥立交危化品事故应急疏散研究范围图 (优化版)
Figure 1(a): Study Area Map for Emergency Evacuation of Hazardous Chemical
             Accident at Taihe Bridge Interchange on 6th Ring Road

优化内容:
  1. 从 POI 数据自动筛选三级医院并标注
  2. 移除左下角北京范围 inset 小图
  3. 扩大显示范围，完整展示亦庄区域
  4. 全面优化配色、线条和图例样式

依赖安装：
pip install geopandas matplotlib shapely pyproj numpy pandas
"""

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.font_manager import FontProperties
import matplotlib.patheffects as pe
from shapely.geometry import Point, box
from shapely.ops import unary_union
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 0. 全局设置
# ============================================================
plt.rcParams['font.sans-serif'] = [
    'Songti SC', 'STSong', 'SimSun', 'Noto Serif CJK SC',
    'PingFang SC', 'Heiti SC', 'SimHei', 'Microsoft YaHei',
    'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'DejaVu Sans'
]
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.size'] = 9

# ============================================================
# 1. 数据路径配置（请根据实际路径修改）
# ============================================================
ROAD_SHP = "/Users/liangwang/12-数据/16-openstreetmap/0original/beijingroaddata.shp"
YIZHUANG_SHP = "/Volumes/WLSSD990/0-百度数据预处理程序/shp/亦庄控规界.shp"
METRO_ROUTE_SHP = "/Users/liangwang/0-成果转化/01-论文/37-地铁时序数据集/2-数据/metro_routes.shp"
METRO_STOP_SHP = "/Users/liangwang/0-成果转化/01-论文/37-地铁时序数据集/2-数据/metro_stops_with_opening_years.shp"
POI_FILE = "/Users/liangwang/12-数据/33-POI数据/POI202206_北京.txt"

# ============================================================
# 2. 核心参数
# ============================================================
ACCIDENT_LON = 116.494
ACCIDENT_LAT = 39.736
BUFFER_RADIUS_KM = 15

CRS_WGS84 = "EPSG:4326"
CRS_PROJ = "EPSG:32650"  # UTM zone 50N

# ★ 扩大纵向范围，完整展示亦庄区域
MAIN_EXTENT = [116.280, 116.870, 39.590, 39.870]

OUTPUT_FILE = "fig1a_study_area_map.png"
OUTPUT_DPI = 300

# ============================================================
# 3. 配色方案（统一管理）
# ============================================================
COLORS = {
    # 研究区域
    'study_area_fill':     '#B3D4F0',   # 淡蓝色填充
    'study_area_edge':     '#1A5694',   # 深蓝色边界
    'buffer_dash':         '#444444',   # 缓冲圈虚线
    'yizhuang_edge':       '#1A5694',   # 亦庄控规界
    # 道路
    'motorway':            '#C07020',   # 六环路 - 深土橙
    'motorway_outline':    '#8B4513',   # 六环路描边
    'trunk':               '#E8A838',   # 干道/高速 - 橙黄
    'primary':             '#D4A460',   # 主要道路
    'secondary':           '#C8C8C8',   # 次要道路
    'tertiary':            '#D8D8D8',   # 三级道路
    'residential':         '#E8E8E8',   # 住宅道路
    # 地铁
    'metro_green':         '#00A65A',   # 地铁线路（亦庄线、5号线）
    'metro_purple':        '#8E44AD',   # 地铁线路（大兴线、10号线）
    # 设施
    'hospital':            '#E31A1C',   # 医疗设施 - 鲜红
    'emergency_depot':     '#D62728',   # 应急储备 - 深红
    'school':              '#555555',   # 学校
    'elderly':             '#777777',   # 养老机构
    'community':           '#666666',   # 居民社区
    'industrial':          '#999999',   # 工业园区
    # 河流
    'river':               '#5B9BD5',   # 河流
    'river_text':          '#2E6EA6',   # 河流文字
    # 爆炸标记
    'explosion_fill':      '#FF0000',
    'explosion_edge':      '#8B0000',
    'explosion_center':    '#FFD700',
    # 文字
    'label_text':          '#333333',
    'place_text':          '#555555',
    # 背景
    'outside_study':       '#F5F0E8',   # 研究区外底色
}

# ============================================================
# 4. 辅助函数
# ============================================================
def load_shp_safe(path, crs_target=CRS_WGS84):
    """安全加载 shapefile"""
    try:
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            gdf = gdf.set_crs(CRS_WGS84)
        gdf = gdf.to_crs(crs_target)
        return gdf
    except Exception as e:
        print(f"[WARNING] 无法加载 {path}: {e}")
        return None


def create_buffer_circle(lon, lat, radius_km, crs_proj=CRS_PROJ):
    """创建缓冲圈"""
    pt = gpd.GeoSeries([Point(lon, lat)], crs=CRS_WGS84).to_crs(crs_proj)
    buf = pt.buffer(radius_km * 1000)
    return buf.to_crs(CRS_WGS84)


def create_study_area(buffer_geom, yizhuang_gdf, crs_proj=CRS_PROJ):
    """研究区域 = 15 km 事故缓冲区 ∪ 亦庄控规界的 15 km 缓冲区"""
    buf_proj = buffer_geom.to_crs(crs_proj)
    if yizhuang_gdf is not None:
        yz_proj = yizhuang_gdf.to_crs(crs_proj)
        yz_buf = yz_proj.buffer(BUFFER_RADIUS_KM * 1000)
        union = unary_union(list(buf_proj) + list(yz_buf))
    else:
        union = unary_union(list(buf_proj))
    result = gpd.GeoSeries([union], crs=crs_proj).to_crs(CRS_WGS84)
    area_km2 = gpd.GeoSeries([union], crs=crs_proj).area.values[0] / 1e6
    print(f"[INFO] 研究区域面积: {area_km2:.0f} km²")
    return result, area_km2


def classify_hospital_level(type):
    """根据名称初步判断医院等级（参考 step3_poi_filter.py）"""
    if pd.isna(type):
        return '未知'
    name = str(type)
    if any(k in name for k in ['三甲', '三级甲等']):
        return '三甲'
    elif any(k in name for k in ['三乙', '三级乙等']):
        return '三乙'
    elif any(k in name for k in ['三级', '三等']):
        return '三级'
    elif any(k in name for k in ['二甲', '二级甲等']):
        return '二甲'
    elif any(k in name for k in ['二乙', '二级乙等', '二级']):
        return '二级'
    elif any(k in name for k in ['协和', '同仁', '宣武', '朝阳医院', '友谊', '积水潭',
                                   '安贞', '天坛', '中日友好', '北大医院', '人民医院',
                                   '301医院', '解放军总', '阜外', '儿童医院', '妇产医院']):
        return '三甲(推测)'
    elif any(k in name for k in ['中心医院', '区医院', '区人民']):
        return '二甲(推测)'
    elif any(k in name for k in ['社区卫生', '卫生院', '诊所', '门诊部']):
        return '基层'
    else:
        return '待确认'


def is_tertiary_hospital(level):
    """判断是否为三级医院"""
    return level in ['三甲', '三甲(推测)', '三乙', '三级']


# ============================================================
# 5. 加载数据
# ============================================================
print("=" * 60)
print("加载数据...")
print("=" * 60)

# 5.1 道路
roads_gdf = load_shp_safe(ROAD_SHP)
if roads_gdf is not None:
    print(f"  道路数据: {len(roads_gdf)} 条记录")
    motorway = roads_gdf[roads_gdf['fclass'].isin(['motorway', 'motorway_link'])]
    trunk = roads_gdf[roads_gdf['fclass'].isin(['trunk', 'trunk_link'])]
    primary = roads_gdf[roads_gdf['fclass'].isin(['primary', 'primary_link'])]
    secondary = roads_gdf[roads_gdf['fclass'].isin(['secondary', 'secondary_link'])]
    tertiary = roads_gdf[roads_gdf['fclass'].isin(['tertiary', 'tertiary_link'])]
    residential = roads_gdf[roads_gdf['fclass'].isin([
        'residential', 'unclassified', 'service', 'living_street'
    ])]
else:
    motorway = trunk = primary = secondary = tertiary = residential = None

# 5.2 亦庄控规界
yizhuang_gdf = load_shp_safe(YIZHUANG_SHP)
if yizhuang_gdf is not None:
    print(f"  亦庄控规界: {len(yizhuang_gdf)} 个多边形")

# 5.3 地铁线路
metro_routes = load_shp_safe(METRO_ROUTE_SHP)
if metro_routes is not None:
    print(f"  地铁线路: {len(metro_routes)} 条")

# 5.4 地铁站点
metro_stops = load_shp_safe(METRO_STOP_SHP)
if metro_stops is not None:
    print(f"  地铁站点: {len(metro_stops)} 个")

# ============================================================
# 6. 生成研究区域
# ============================================================
print("\n生成研究区域...")
buffer_geom = create_buffer_circle(ACCIDENT_LON, ACCIDENT_LAT, BUFFER_RADIUS_KM)
study_area, area_km2 = create_study_area(buffer_geom, yizhuang_gdf)

# ============================================================
# 7. 从 POI 数据筛选三级医院
# ============================================================
print("\n从 POI 数据筛选三级医院...")

tertiary_hospitals = []  # 存储三级医院列表

try:
    poi_df = pd.read_csv(POI_FILE, sep='\t', dtype=str, quoting=3)
    # 清洗列名
    poi_df.columns = [c.strip('"').strip() for c in poi_df.columns]
    for col in poi_df.columns:
        if poi_df[col].dtype == object:
            poi_df[col] = poi_df[col].str.strip('"').str.strip()

    # 转坐标
    poi_df['lon'] = pd.to_numeric(poi_df['longitude_wgs84'], errors='coerce')
    poi_df['lat'] = pd.to_numeric(poi_df['latitude_wgs84'], errors='coerce')
    poi_df = poi_df.dropna(subset=['lon', 'lat'])

    # 粗筛到研究区域
    mask = (
        (poi_df['lon'] >= MAIN_EXTENT[0]) &
        (poi_df['lon'] <= MAIN_EXTENT[1]) &
        (poi_df['lat'] >= MAIN_EXTENT[2]) &
        (poi_df['lat'] <= MAIN_EXTENT[3])
    )
    poi_local = poi_df[mask].copy()
    print(f"  研究区域内 POI: {len(poi_local)} 个")

    # 筛选医院
    hospitals_poi = poi_local[
        (poi_local['大类'].str.contains('医疗', na=False)) &
        (poi_local['中类'].str.contains('医院|急救', na=False))
    ].copy()

    if len(hospitals_poi) > 0:
        hospitals_poi['hospital_level'] = hospitals_poi['name'].apply(classify_hospital_level)
        # 只保留三级医院
        tertiary_mask = hospitals_poi['hospital_level'].apply(is_tertiary_hospital)
        tertiary_df = hospitals_poi[tertiary_mask].copy()
        print(f"  找到医院: {len(hospitals_poi)} 家，其中三级医院: {len(tertiary_df)} 家")

        for _, row in tertiary_df.iterrows():
            tertiary_hospitals.append({
                'name': row['name'],
                'lon': row['lon'],
                'lat': row['lat'],
                'level': row['hospital_level'],
            })
            print(f"    ★ {row['name']} ({row['hospital_level']}) @ ({row['lon']:.3f}, {row['lat']:.3f})")
    else:
        print("  未筛选到医院，将使用备用标注")

except Exception as e:
    print(f"  [WARNING] POI 数据加载失败: {e}")
    print("  将使用备用手动标注的医院数据")

# 如果 POI 未筛到，使用备用数据
if len(tertiary_hospitals) == 0:
    print("  使用备用三级医院标注...")
    tertiary_hospitals = [
        {'name': '亦庄医院', 'lon': 116.485, 'lat': 39.734, 'level': '待确认'},
        {'name': '大兴区人民医院', 'lon': 116.465, 'lat': 39.728, 'level': '二甲(推测)'},
        {'name': '亦庄医院(分院)', 'lon': 116.510, 'lat': 39.738, 'level': '待确认'},
    ]

# ============================================================
# 8. 其他关键设施（手动标注）
# ============================================================
KEY_FACILITIES = {
    '应急物资储备库': [
        {'name': '通州物资储备库', 'lon': 116.530, 'lat': 39.730},
        {'name': '通州物资储备库(北)', 'lon': 116.490, 'lat': 39.772},
    ],
    '弱势设施': [
        {'name': '聘物学校', 'lon': 116.440, 'lat': 39.720, 'sub': 'school'},
        {'name': '护理养生家', 'lon': 116.470, 'lat': 39.715, 'sub': 'elderly'},
    ],
    '居民社区': [
        {'name': '住居社区', 'lon': 116.448, 'lat': 39.718},
        {'name': '大兴区旧\n居住区', 'lon': 116.488, 'lat': 39.770},
    ],
    '工业园区': [
        {'name': '工业园区', 'lon': 116.470, 'lat': 39.708},
    ],
}

# 河流
RIVERS = {
    '文玉河': [(116.400, 39.735), (116.430, 39.738), (116.460, 39.742),
               (116.475, 39.748), (116.485, 39.752)],
    '凉水河': [(116.430, 39.725), (116.460, 39.730), (116.490, 39.735),
               (116.510, 39.745), (116.530, 39.755)],
    '文惠河': [(116.488, 39.700), (116.492, 39.715), (116.494, 39.730),
               (116.496, 39.742)],
}

# ============================================================
# 9. 绘图
# ============================================================
print("\n" + "=" * 60)
print("开始绘图...")
print("=" * 60)

# ★ 加大图幅，宽高比改为更纵向，完整显示亦庄
fig = plt.figure(figsize=(16, 18))

# ★ 移除 inset，主图区域占更大面积
ax_main = fig.add_axes([0.04, 0.05, 0.73, 0.88])
# 图例区域
ax_legend = fig.add_axes([0.78, 0.12, 0.21, 0.76])
ax_legend.axis('off')

# ----------------------------------------------------------
# 9.1 底色：研究区外灰白底，研究区内蓝色填充
# ----------------------------------------------------------
ax_main.set_facecolor(COLORS['outside_study'])

study_area.plot(ax=ax_main, color=COLORS['study_area_fill'], alpha=0.50,
                edgecolor='none', zorder=2)

# 15 km 缓冲圈（虚线）
buffer_geom.plot(ax=ax_main, facecolor='none', edgecolor=COLORS['buffer_dash'],
                 linewidth=1.3, linestyle=(0, (8, 4)), zorder=3, label='15 km 缓冲区')

# 亦庄控规界（醒目蓝色实线）
if yizhuang_gdf is not None:
    yizhuang_gdf.plot(ax=ax_main, facecolor='none', edgecolor=COLORS['yizhuang_edge'],
                      linewidth=2.2, zorder=4, linestyle='-')

# 研究区域外轮廓
study_area.plot(ax=ax_main, facecolor='none', edgecolor=COLORS['study_area_edge'],
                linewidth=1.8, zorder=4)

# ----------------------------------------------------------
# 9.2 道路网络
# ----------------------------------------------------------
clip_box = box(MAIN_EXTENT[0] - 0.02, MAIN_EXTENT[2] - 0.02,
               MAIN_EXTENT[1] + 0.02, MAIN_EXTENT[3] + 0.02)

def plot_roads_clipped(gdf, ax, clip_geom, **kwargs):
    if gdf is not None and len(gdf) > 0:
        clipped = gpd.clip(gdf, clip_geom)
        if len(clipped) > 0:
            clipped.plot(ax=ax, **kwargs)

# 由底到顶分层绘制
plot_roads_clipped(residential, ax_main, clip_box,
                   color=COLORS['residential'], linewidth=0.2, zorder=5)
plot_roads_clipped(tertiary, ax_main, clip_box,
                   color=COLORS['tertiary'], linewidth=0.3, zorder=6)
plot_roads_clipped(secondary, ax_main, clip_box,
                   color=COLORS['secondary'], linewidth=0.5, zorder=7)
plot_roads_clipped(primary, ax_main, clip_box,
                   color=COLORS['primary'], linewidth=0.8, zorder=8)
# 干道（橙黄粗线 + 浅描边）
plot_roads_clipped(trunk, ax_main, clip_box,
                   color=COLORS['trunk'], linewidth=2.2, zorder=9)
# 六环路/高速（深橙描边 + 主色）
plot_roads_clipped(motorway, ax_main, clip_box,
                   color=COLORS['motorway_outline'], linewidth=3.5, zorder=10)
plot_roads_clipped(motorway, ax_main, clip_box,
                   color=COLORS['motorway'], linewidth=2.5, zorder=10)

# ----------------------------------------------------------
# 9.3 地铁线路
# ----------------------------------------------------------
if metro_routes is not None:
    metro_clipped = gpd.clip(metro_routes, clip_box)
    if len(metro_clipped) > 0:
        for idx, row in metro_clipped.iterrows():
            name = str(row.get('name', row.get('route_name', row.get('NAME', ''))))
            if '亦庄' in name or '5' in name:
                color, lw = COLORS['metro_green'], 2.0
            elif '大兴' in name or '10' in name:
                color, lw = COLORS['metro_purple'], 1.8
            else:
                color, lw = COLORS['metro_green'], 1.5
            gpd.GeoSeries([row.geometry]).plot(ax=ax_main, color=color, linewidth=lw, zorder=11)

# 地铁站点
if metro_stops is not None:
    stops_clipped = gpd.clip(metro_stops, clip_box)
    if len(stops_clipped) > 0:
        stops_clipped.plot(ax=ax_main, color=COLORS['metro_green'], markersize=8,
                          marker='o', zorder=12, edgecolor='white', linewidth=0.4)

# ----------------------------------------------------------
# 9.4 河流
# ----------------------------------------------------------
for river_name, coords in RIVERS.items():
    xs, ys = zip(*coords)
    ax_main.plot(xs, ys, color=COLORS['river'], linewidth=1.8, zorder=5,
                alpha=0.75, linestyle='-', solid_capstyle='round')
    mid = len(coords) // 2
    rotation = 80 if '文惠' in river_name else -8
    ax_main.annotate(river_name, xy=coords[mid], fontsize=7,
                    color=COLORS['river_text'], style='italic',
                    ha='center', va='bottom', zorder=15,
                    rotation=rotation,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground='white')])

# ----------------------------------------------------------
# 9.5 爆炸标记（事故中心点）
# ----------------------------------------------------------
# 更精致的爆炸星形
n_pts = 16
explosion_angles = np.linspace(0, 2 * np.pi, n_pts + 1)[:-1]
r_outer, r_inner = 0.0055, 0.0025
ex, ey = [], []
for i, angle in enumerate(explosion_angles):
    r = r_outer if i % 2 == 0 else r_inner
    ex.append(ACCIDENT_LON + r * np.cos(angle) * 0.6)
    ey.append(ACCIDENT_LAT + r * np.sin(angle))

ax_main.fill(ex, ey, color=COLORS['explosion_fill'], zorder=20,
            edgecolor=COLORS['explosion_edge'], linewidth=1.2)
ax_main.plot(ACCIDENT_LON, ACCIDENT_LAT, 'o', color=COLORS['explosion_center'],
            markersize=4, zorder=21)

# 坐标标注
ax_main.annotate(
    f'(116.494°E, 39.736°N)',
    xy=(ACCIDENT_LON, ACCIDENT_LAT),
    xytext=(ACCIDENT_LON + 0.014, ACCIDENT_LAT + 0.010),
    fontsize=8, fontweight='bold', color=COLORS['label_text'],
    arrowprops=dict(arrowstyle='->', color=COLORS['label_text'], lw=0.8),
    zorder=22,
    bbox=dict(boxstyle='round,pad=0.25', facecolor='white', alpha=0.85, edgecolor='#CCCCCC', linewidth=0.5)
)

# ----------------------------------------------------------
# 9.6 ★ 三级医院标注（从 POI 筛选或备用数据）
# ----------------------------------------------------------
print(f"\n标注三级医院 ({len(tertiary_hospitals)} 家)...")
for hosp in tertiary_hospitals:
    # 红色十字圆圈标记
    ax_main.plot(hosp['lon'], hosp['lat'], marker='P', color=COLORS['hospital'],
                markersize=11, markeredgecolor='white', markeredgewidth=0.8, zorder=18)
    # 名称标注
    # 简化过长名称
    display_name = hosp['name']
    if len(display_name) > 10:
        display_name = display_name[:10] + '\n' + display_name[10:]
    ax_main.annotate(display_name, xy=(hosp['lon'], hosp['lat']),
                    xytext=(6, -14), textcoords='offset points',
                    fontsize=6.5, color=COLORS['label_text'], zorder=19,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                             alpha=0.80, edgecolor='#DDDDDD', linewidth=0.3))

# ----------------------------------------------------------
# 9.7 其他设施标注
# ----------------------------------------------------------
# 应急物资储备库
for fac in KEY_FACILITIES['应急物资储备库']:
    ax_main.plot(fac['lon'], fac['lat'], marker='s', color=COLORS['emergency_depot'],
                markersize=8, zorder=18, markeredgecolor='#333333', markeredgewidth=0.6)
    ax_main.annotate(fac['name'], xy=(fac['lon'], fac['lat']),
                    xytext=(6, 5), textcoords='offset points',
                    fontsize=6.5, color=COLORS['label_text'], zorder=19,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                             alpha=0.80, edgecolor='#DDDDDD', linewidth=0.3))

# 弱势设施
for fac in KEY_FACILITIES['弱势设施']:
    ax_main.plot(fac['lon'], fac['lat'], marker='s', color=COLORS['school'],
                markersize=6, zorder=18, markeredgecolor='#333333', markeredgewidth=0.4)
    ax_main.annotate(fac['name'], xy=(fac['lon'], fac['lat']),
                    xytext=(5, -12), textcoords='offset points',
                    fontsize=6, color=COLORS['label_text'], zorder=19,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                             alpha=0.75, edgecolor='none'))

# 居民社区
for fac in KEY_FACILITIES['居民社区']:
    ax_main.plot(fac['lon'], fac['lat'], marker='^', color=COLORS['community'],
                markersize=7, zorder=18, markeredgecolor='#333333', markeredgewidth=0.4)
    ax_main.annotate(fac['name'], xy=(fac['lon'], fac['lat']),
                    xytext=(5, -12), textcoords='offset points',
                    fontsize=6, color=COLORS['label_text'], zorder=19,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                             alpha=0.75, edgecolor='none'))

# 工业园区
for fac in KEY_FACILITIES['工业园区']:
    ax_main.plot(fac['lon'], fac['lat'], marker='D', color=COLORS['industrial'],
                markersize=6, zorder=18, markeredgecolor='#333333', markeredgewidth=0.4)
    ax_main.annotate(fac['name'], xy=(fac['lon'], fac['lat']),
                    xytext=(5, -12), textcoords='offset points',
                    fontsize=6, color=COLORS['label_text'], zorder=19,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                             alpha=0.75, edgecolor='none'))

# ----------------------------------------------------------
# 9.8 地铁线路名称标注
# ----------------------------------------------------------
metro_labels = [
    {'name': '亦庄线', 'lon': 116.470, 'lat': 39.750, 'rotation': 45, 'color': COLORS['metro_green']},
    {'name': '大兴线', 'lon': 116.420, 'lat': 39.755, 'rotation': 80, 'color': COLORS['metro_purple']},
    {'name': '5号线', 'lon': 116.473, 'lat': 39.735, 'rotation': 70, 'color': COLORS['metro_green']},
    {'name': '10号线', 'lon': 116.500, 'lat': 39.720, 'rotation': 60, 'color': COLORS['metro_purple']},
]
for ml in metro_labels:
    ax_main.annotate(ml['name'], xy=(ml['lon'], ml['lat']),
                    fontsize=7, color=ml['color'], rotation=ml['rotation'],
                    fontstyle='italic', fontweight='bold', zorder=16,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground='white')])

# ----------------------------------------------------------
# 9.9 地名标注
# ----------------------------------------------------------
place_labels = [
    {'name': '大兴区旧\n宫镇', 'lon': 116.490, 'lat': 39.770, 'fs': 8.5},
    {'name': '北京研究范围', 'lon': 116.415, 'lat': 39.755, 'fs': 8.5},
    {'name': '北兴高速路', 'lon': 116.340, 'lat': 39.740, 'fs': 7},
    {'name': '京沪高速路', 'lon': 116.460, 'lat': 39.700, 'fs': 7},
]
for pl in place_labels:
    ax_main.annotate(pl['name'], xy=(pl['lon'], pl['lat']),
                    fontsize=pl['fs'], color=COLORS['place_text'], ha='center',
                    zorder=15,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground='white')])

# ----------------------------------------------------------
# 9.10 设置范围和坐标轴
# ----------------------------------------------------------
ax_main.set_xlim(MAIN_EXTENT[0], MAIN_EXTENT[1])
ax_main.set_ylim(MAIN_EXTENT[2], MAIN_EXTENT[3])

ax_main.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.3f}°E'))
ax_main.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.2f}°N'))
ax_main.tick_params(labelsize=8, direction='in', length=4, width=0.6)
ax_main.grid(True, linestyle=':', alpha=0.25, color='#888888', linewidth=0.4)

# 主图边框
for spine in ax_main.spines.values():
    spine.set_linewidth(0.8)
    spine.set_color('#555555')

# ----------------------------------------------------------
# 9.11 比例尺
# ----------------------------------------------------------
scale_x0 = MAIN_EXTENT[0] + 0.10
scale_y0 = MAIN_EXTENT[2] + 0.015
deg_per_km_lon = 1 / 85.3
scale_lengths = [0, 5, 10, 20]
for i in range(len(scale_lengths) - 1):
    x0 = scale_x0 + scale_lengths[i] * deg_per_km_lon
    x1 = scale_x0 + scale_lengths[i + 1] * deg_per_km_lon
    color = '#333333' if i % 2 == 0 else 'white'
    ax_main.fill_between([x0, x1], scale_y0, scale_y0 + 0.0028,
                        color=color, edgecolor='#333333', linewidth=0.5, zorder=25)
    ax_main.text(x0, scale_y0 - 0.004, f'{scale_lengths[i]}',
                fontsize=6, ha='center', zorder=25, color='#333333')
ax_main.text(scale_x0 + scale_lengths[-1] * deg_per_km_lon,
            scale_y0 - 0.004, f'{scale_lengths[-1]}  Km',
            fontsize=6, ha='center', zorder=25, color='#333333')

# 指北针
north_x = MAIN_EXTENT[0] + 0.035
north_y = MAIN_EXTENT[3] - 0.03
ax_main.annotate('N', xy=(north_x, north_y + 0.016),
                fontsize=11, fontweight='bold', ha='center', zorder=25, color='#333333')
ax_main.annotate('', xy=(north_x, north_y + 0.015),
                xytext=(north_x, north_y),
                arrowprops=dict(arrowstyle='->', lw=1.8, color='#333333'),
                zorder=25)

# ----------------------------------------------------------
# 9.12 图例
# ----------------------------------------------------------
y_start = 0.97
dy = 0.042

ax_legend.text(0.05, y_start, '图  例', fontsize=12, fontweight='bold',
              transform=ax_legend.transAxes, va='top')
y = y_start - 0.06

# --- 事故中心点 ---
ax_legend.plot(0.08, y, marker='*', color=COLORS['explosion_fill'], markersize=14,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '事故中心点：太和桥立', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 六环路 ---
ax_legend.plot([0.03, 0.15], [y, y], color=COLORS['motorway'], linewidth=3.5,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '太环路立交', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 主要高速 ---
ax_legend.plot([0.03, 0.15], [y, y], color=COLORS['trunk'], linewidth=2.8,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '主义高速', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 地铁线路（绿） ---
ax_legend.plot([0.03, 0.15], [y, y], color=COLORS['metro_green'], linewidth=2.2,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '地铁线路', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 地铁线（紫） ---
ax_legend.plot([0.03, 0.15], [y, y], color=COLORS['metro_purple'], linewidth=2.2,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '地铁线', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 三级医院 ---
ax_legend.plot(0.08, y, marker='P', color=COLORS['hospital'], markersize=10,
              markeredgecolor='white', markeredgewidth=0.6,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '三级医院', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 应急物资储备库 ---
ax_legend.plot(0.08, y, marker='s', color=COLORS['emergency_depot'], markersize=7,
              transform=ax_legend.transAxes, zorder=5,
              markeredgecolor='#333333', markeredgewidth=0.5)
ax_legend.text(0.20, y, '应急物资储备库', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 弱势设施 ---
ax_legend.plot(0.08, y, marker='s', color=COLORS['school'], markersize=6,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '弱势设施', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 居民社区 ---
ax_legend.plot(0.08, y, marker='^', color=COLORS['community'], markersize=7,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '居民社区', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 工业园区 ---
ax_legend.plot(0.08, y, marker='D', color=COLORS['industrial'], markersize=6,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '工业园区', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 15 km 缓冲区 ---
ax_legend.plot([0.03, 0.15], [y, y], color=COLORS['buffer_dash'], linewidth=1.3,
              linestyle=(0, (8, 4)), transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '15 km 半径缓冲区', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 亦庄控规界 ---
ax_legend.plot([0.03, 0.15], [y, y], color=COLORS['yizhuang_edge'], linewidth=2.2,
              transform=ax_legend.transAxes, zorder=5)
ax_legend.text(0.20, y, '亦庄控规界', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy

# --- 最终研究范围 ---
rect = Rectangle((0.03, y - 0.015), 0.12, 0.03,
                transform=ax_legend.transAxes,
                facecolor=COLORS['study_area_fill'], alpha=0.55,
                edgecolor=COLORS['study_area_edge'], linewidth=1.2)
ax_legend.add_patch(rect)
ax_legend.text(0.20, y, f'最终研究范围 (约{area_km2:.0f}\nkm²)', fontsize=7.5,
              transform=ax_legend.transAxes, va='center')
y -= dy * 1.5

# --- 坐标信息 ---
ax_legend.text(0.05, y, '坐标标准字: WGS 1984', fontsize=6.5,
              transform=ax_legend.transAxes, va='center', color='#666666')
y -= dy * 0.65
ax_legend.text(0.05, y, '统一投影字: WGS 1984', fontsize=6.5,
              transform=ax_legend.transAxes, va='center', color='#666666')
y -= dy * 0.65
ax_legend.text(0.05, y, 'Coordinateste, projected', fontsize=6.5,
              transform=ax_legend.transAxes, va='center', color='#666666',
              fontstyle='italic')

# 图例面板样式
ax_legend.patch.set_edgecolor('#AAAAAA')
ax_legend.patch.set_linewidth(1)
ax_legend.patch.set_visible(True)
ax_legend.patch.set_facecolor('#FCFCFC')

# ----------------------------------------------------------
# 9.13 标题
# ----------------------------------------------------------
fig.suptitle('图 1(a): 六环路太和桥立交危化品事故应急疏散研究范围图',
            fontsize=15, fontweight='bold', y=0.97)

# ----------------------------------------------------------
# 9.14 保存
# ----------------------------------------------------------
plt.savefig(OUTPUT_FILE, dpi=OUTPUT_DPI, bbox_inches='tight',
           facecolor='white', edgecolor='none')
print(f"\n[DONE] 图片已保存: {OUTPUT_FILE}")
print(f"  分辨率: {OUTPUT_DPI} DPI")
plt.close()

print("\n" + "=" * 60)
print("完成！")
print("=" * 60)