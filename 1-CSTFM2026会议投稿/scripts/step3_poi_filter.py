"""
Step 3: POI 数据筛选（严格小类版）
==================================
功能：
  1. 读取 POI 数据并裁剪到研究范围
  2. 按「小类」严格筛选五类应急设施
  3. 打印筛选前后的小类分布（方便调试）
  4. 可视化

筛选规则（基于小类字段）：
  医院:     综合医院、三级甲等医院、急救中心、胸科医院、眼科医院、卫生院、专科医院、肿瘤医院
  消防站:   消防机关
  避难场所: 公园、城市广场、综合体育馆、体育休闲服务场所、篮球场馆、足球场、
            运动场所、游泳馆、网球场、羽毛球场、健身中心、户外健身场所、露营地
  地铁站:   地铁站
  脆弱设施: 小学、中学、高中、幼儿园、福利院、养老院

前置条件：先运行 step0_study_area.py
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from shapely.geometry import Point
import warnings
warnings.filterwarnings('ignore')
from config import *

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


# ==================== 筛选规则（严格按小类）====================

# 医院：能接收危化品中毒伤员的医疗机构
HOSPITAL_SUBCATS = [
    '综合医院',       # 主要接收机构
    '三级甲等医院',   # 高等级综合
    '急救中心',       # 急诊急救
    '胸科医院',       # 氯气→呼吸道损伤
    '眼科医院',       # 氯气→眼部刺激
    '卫生院',         # 基层分诊
    '专科医院',       # 部分可接收
    '肿瘤医院',       # 有急诊能力
]

# 消防站：仅消防机关（排除消防器材店等）
FIRE_SUBCATS = ['消防机关']

# 避难场所：有足够面积和容量的开放/半开放空间
SHELTER_SUBCATS = [
    # 室外大型
    '公园',           '城市广场',       '公园广场',
    '户外健身场所',   '露营地',
    # 体育场馆
    '综合体育馆',     '体育休闲服务场所',
    '篮球场馆',       '足球场',         '运动场所',
    '游泳馆',         '网球场',         '羽毛球场',
    '乒乓球馆',       '健身中心',
]

# 地铁站
SUBWAY_SUBCATS = ['地铁站']

# 脆弱性设施：需要优先疏散的弱势群体聚集地
VULNERABLE_SUBCATS = [
    '小学', '中学', '高中',   # 学校
    '幼儿园',                  # 幼儿
    '福利院', '养老院',        # 老人/残障
]


# ==================== 辅助函数 ====================

def load_study_area():
    sa_path = os.path.join(DIRS['study_area'], "study_area_buffer.shp")
    core_path = os.path.join(DIRS['study_area'], "yizhuang_boundary.shp")
    incident_path = os.path.join(DIRS['study_area'], "incident_point.shp")
    return gpd.read_file(sa_path), gpd.read_file(core_path), gpd.read_file(incident_path)


def filter_by_subcat(poi_gdf, subcats, label):
    """按小类字段严格筛选"""
    result = poi_gdf[poi_gdf['小类'].isin(subcats)].copy()
    print(f"  {label}: 匹配 {len(result)} 条 (规则: {len(subcats)} 个小类)")
    if len(result) > 0:
        sub_counts = result['小类'].value_counts()
        for sc, cnt in sub_counts.items():
            print(f"    {sc}: {cnt}")
    return result


def classify_hospital_level(name):
    """根据名称初步判断医院等级"""
    if pd.isna(name):
        return '未知'
    name = str(name)
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
                                   '301医院', '解放军总', '阜外', '儿童医院', '妇产医院',
                                   '东方医院']):
        return '三甲(推测)'
    elif any(k in name for k in ['中心医院', '区医院', '区人民']):
        return '二甲(推测)'
    elif any(k in name for k in ['社区卫生', '卫生院', '诊所', '门诊部', '服务站']):
        return '基层'
    else:
        return '待确认'


def estimate_bed_count(level):
    bed_map = {
        '三甲': 1500, '三甲(推测)': 1500, '三乙': 800, '三级': 1000,
        '二甲': 400, '二甲(推测)': 400, '二级': 300,
        '基层': 50, '待确认': 200, '未知': 100
    }
    return bed_map.get(level, 100)


def estimate_emergency_capacity(level):
    cap_map = {
        '三甲': 50, '三甲(推测)': 50, '三乙': 30, '三级': 40,
        '二甲': 20, '二甲(推测)': 20, '二级': 15,
        '基层': 5, '待确认': 10, '未知': 5
    }
    return cap_map.get(level, 5)


def estimate_shelter_capacity(name, subcat):
    """根据名称和小类估算避难容量"""
    name = str(name) if not pd.isna(name) else ''
    subcat = str(subcat) if not pd.isna(subcat) else ''
    if subcat in ['公园', '城市广场', '公园广场']:
        if any(k in name for k in ['体育场', '运动场', '奥林匹克']):
            return 15000
        elif any(k in name for k in ['公园']):
            return 5000
        elif any(k in name for k in ['广场']):
            return 8000
        return 3000
    elif subcat == '综合体育馆':
        return 5000
    elif subcat in ['足球场', '运动场所', '体育休闲服务场所']:
        return 3000
    elif subcat in ['篮球场馆', '游泳馆']:
        return 2000
    elif subcat in ['网球场', '羽毛球场', '乒乓球馆']:
        return 500
    elif subcat in ['健身中心', '户外健身场所']:
        return 300
    elif subcat == '露营地':
        return 1000
    else:
        return 500


# ==================== 主函数 ====================

def main():
    print("=" * 60)
    print("Step 3: POI 数据筛选（严格小类版）")
    print("=" * 60)

    study_area, core, incident = load_study_area()
    study_polygon = study_area.geometry.values[0]
    out_dir = DIRS['poi']
    fig_dir = DIRS['figures']

    # ------------------------------------------------------------------
    # 1. 读取 POI 数据
    # ------------------------------------------------------------------
    print("\n[1/7] 读取 POI 数据...")
    poi = pd.read_csv(POI_FILE, sep="\t", dtype=str, quoting=3)

    poi.columns = [c.strip('"').strip() for c in poi.columns]
    for col in poi.columns:
        if poi[col].dtype == object:
            poi[col] = poi[col].str.strip('"').str.strip()

    print(f"  POI 总数: {len(poi)}")
    print(f"  列名: {list(poi.columns)}")

    poi['lon'] = pd.to_numeric(poi['longitude_wgs84'], errors='coerce')
    poi['lat'] = pd.to_numeric(poi['latitude_wgs84'], errors='coerce')
    poi = poi.dropna(subset=['lon', 'lat'])

    poi_gdf = gpd.GeoDataFrame(
        poi, geometry=gpd.points_from_xy(poi.lon, poi.lat), crs=WGS84_CRS
    )

    print("  裁剪到研究范围...")
    poi_study = gpd.clip(poi_gdf, study_polygon)
    print(f"  研究范围内 POI 数: {len(poi_study)}")

    # 打印小类分布概览
    print(f"\n  小类总数: {poi_study['小类'].nunique()}")

    # ------------------------------------------------------------------
    # 2. 筛选医院
    # ------------------------------------------------------------------
    print("\n[2/7] 筛选医院...")
    print(f"  筛选小类: {HOSPITAL_SUBCATS}")

    # 先打印研究范围内所有医疗相关小类（调试用）
    medical_poi = poi_study[poi_study['大类'].str.contains('医疗', na=False)]
    if len(medical_poi) > 0:
        print(f"  研究范围内医疗大类 POI: {len(medical_poi)}")
        print(f"  医疗小类分布:")
        for sc, cnt in medical_poi['小类'].value_counts().items():
            flag = "✅" if sc in HOSPITAL_SUBCATS else "  "
            print(f"    {flag} {sc}: {cnt}")

    hospitals = filter_by_subcat(poi_study, HOSPITAL_SUBCATS, "医院")

    if len(hospitals) > 0:
        hospitals['hospital_level'] = hospitals['name'].apply(classify_hospital_level)
        hospitals['bed_count'] = hospitals['hospital_level'].apply(estimate_bed_count)
        hospitals['emergency_cap'] = hospitals['hospital_level'].apply(estimate_emergency_capacity)
        print(f"\n  医院等级分布:")
        for lv, cnt in hospitals['hospital_level'].value_counts().items():
            print(f"    {lv}: {cnt} 家")

    # ------------------------------------------------------------------
    # 3. 筛选消防站
    # ------------------------------------------------------------------
    print("\n[3/7] 筛选消防站...")
    print(f"  筛选小类: {FIRE_SUBCATS}")

    # 打印所有消防相关小类
    fire_related = poi_study[
        (poi_study['name'].str.contains('消防', na=False)) |
        (poi_study['中类'].str.contains('消防', na=False)) |
        (poi_study['小类'].str.contains('消防', na=False))
    ]
    if len(fire_related) > 0:
        print(f"  研究范围内消防相关 POI: {len(fire_related)}")
        print(f"  消防小类分布:")
        for sc, cnt in fire_related['小类'].value_counts().items():
            flag = "✅" if sc in FIRE_SUBCATS else "  "
            print(f"    {flag} {sc}: {cnt}")

    fire_stations = filter_by_subcat(poi_study, FIRE_SUBCATS, "消防站")
    if len(fire_stations) > 0:
        fire_stations['fire_trucks'] = 5
        fire_stations['ambulances'] = 2

    # ------------------------------------------------------------------
    # 4. 筛选避难场所
    # ------------------------------------------------------------------
    print("\n[4/7] 筛选避难场所...")
    print(f"  筛选小类: {SHELTER_SUBCATS}")

    # 打印所有休闲/体育相关小类
    leisure_poi = poi_study[
        (poi_study['大类'].str.contains('体育|休闲|旅游', na=False)) |
        (poi_study['中类'].str.contains('公园|广场|体育|运动', na=False))
    ]
    if len(leisure_poi) > 0:
        print(f"  研究范围内休闲体育 POI: {len(leisure_poi)}")
        print(f"  小类分布:")
        for sc, cnt in leisure_poi['小类'].value_counts().head(30).items():
            flag = "✅" if sc in SHELTER_SUBCATS else "  "
            print(f"    {flag} {sc}: {cnt}")

    shelters = filter_by_subcat(poi_study, SHELTER_SUBCATS, "避难场所")
    if len(shelters) > 0:
        shelters = gpd.GeoDataFrame(shelters, geometry='geometry', crs=WGS84_CRS)
        shelters['capacity'] = shelters.apply(
            lambda r: estimate_shelter_capacity(r.get('name', ''), r.get('小类', '')),
            axis=1
        )
        print(f"  预估总容纳人数: {shelters['capacity'].sum():,} 人")
    else:
        shelters = gpd.GeoDataFrame(columns=['name', 'geometry', 'capacity'],
                                     geometry='geometry', crs=WGS84_CRS)

    # ------------------------------------------------------------------
    # 5. 筛选地铁站
    # ------------------------------------------------------------------
    print("\n[5/7] 筛选地铁站...")
    print(f"  筛选小类: {SUBWAY_SUBCATS}")

    # 打印交通相关小类
    transport_poi = poi_study[poi_study['大类'].str.contains('交通', na=False)]
    if len(transport_poi) > 0:
        print(f"  研究范围内交通大类 POI: {len(transport_poi)}")
        subway_related = transport_poi[transport_poi['小类'].str.contains('地铁', na=False)]
        print(f"  地铁相关小类:")
        for sc, cnt in subway_related['小类'].value_counts().items():
            flag = "✅" if sc in SUBWAY_SUBCATS else "  "
            print(f"    {flag} {sc}: {cnt}")

    subway_stations = filter_by_subcat(poi_study, SUBWAY_SUBCATS, "地铁站")
    if len(subway_stations) > 0:
        # 去重（同一站多个出入口）
        subway_stations['station_name'] = subway_stations['name'].str.replace(
            r'[（(].*?[)）]', '', regex=True
        ).str.replace(r'[-—].*', '', regex=True).str.strip()
        n_before = len(subway_stations)
        subway_stations = subway_stations.drop_duplicates(subset=['station_name'])
        print(f"  去重: {n_before} → {len(subway_stations)} 个站")

    # ------------------------------------------------------------------
    # 6. 筛选脆弱性设施
    # ------------------------------------------------------------------
    print("\n[6/7] 筛选脆弱性设施...")
    print(f"  筛选小类: {VULNERABLE_SUBCATS}")

    # 打印教育/福利相关小类
    edu_poi = poi_study[
        (poi_study['大类'].str.contains('科教|政府', na=False)) |
        (poi_study['小类'].str.contains('学|幼儿|养老|福利', na=False))
    ]
    if len(edu_poi) > 0:
        print(f"  教育/福利相关小类:")
        for sc, cnt in edu_poi['小类'].value_counts().head(20).items():
            flag = "✅" if sc in VULNERABLE_SUBCATS else "  "
            print(f"    {flag} {sc}: {cnt}")

    vulnerable = filter_by_subcat(poi_study, VULNERABLE_SUBCATS, "脆弱性设施")
    if len(vulnerable) > 0:
        vulnerable = gpd.GeoDataFrame(vulnerable, geometry='geometry', crs=WGS84_CRS)
        # 标记类型
        type_map = {
            '小学': '学校', '中学': '学校', '高中': '学校',
            '幼儿园': '幼儿园',
            '福利院': '养老/福利', '养老院': '养老/福利',
        }
        vulnerable['type'] = vulnerable['小类'].map(type_map).fillna('其他')
        print(f"\n  按类型统计:")
        for t, cnt in vulnerable['type'].value_counts().items():
            print(f"    {t}: {cnt}")
    else:
        vulnerable = gpd.GeoDataFrame(columns=['name', 'geometry', 'type'],
                                       geometry='geometry', crs=WGS84_CRS)

    # ------------------------------------------------------------------
    # 7. 保存
    # ------------------------------------------------------------------
    print("\n[7/7] 保存文件...")
    hospitals.to_file(os.path.join(out_dir, "hospitals.shp"), encoding='utf-8')
    fire_stations.to_file(os.path.join(out_dir, "fire_stations.shp"), encoding='utf-8')
    shelters.to_file(os.path.join(out_dir, "shelters.shp"), encoding='utf-8')
    if len(subway_stations) > 0:
        subway_stations.to_file(os.path.join(out_dir, "subway_stations.shp"), encoding='utf-8')
    vulnerable.to_file(os.path.join(out_dir, "vulnerable_facilities.shp"), encoding='utf-8')

    # 保存 CSV（方便人工核查）
    for name, gdf in [('hospitals', hospitals), ('fire_stations', fire_stations),
                       ('shelters', shelters), ('subway_stations', subway_stations),
                       ('vulnerable', vulnerable)]:
        if len(gdf) == 0:
            continue
        cols_to_save = ['name', 'address', '大类', '中类', '小类', 'lon', 'lat']
        extra = {'hospitals': ['hospital_level', 'bed_count', 'emergency_cap'],
                 'fire_stations': ['fire_trucks', 'ambulances'],
                 'shelters': ['capacity'],
                 'subway_stations': ['station_name'],
                 'vulnerable': ['type']}
        save_cols = [c for c in cols_to_save + extra.get(name, []) if c in gdf.columns]
        gdf[save_cols].to_csv(
            os.path.join(out_dir, f"{name}_list.csv"), index=False, encoding='utf-8-sig'
        )

    print(f"  ✅ 已保存至 {out_dir}")

    # ------------------------------------------------------------------
    # 可视化
    # ------------------------------------------------------------------
    print("\n正在生成可视化...")
    plot_poi_results(hospitals, fire_stations, shelters, subway_stations,
                     vulnerable, study_area, core, incident, fig_dir)

    # 摘要
    print("\n" + "=" * 60)
    print("Step 3 完成 - 摘要")
    print("=" * 60)
    print(f"  医院:       {len(hospitals):4d} 家  (小类: {', '.join(HOSPITAL_SUBCATS[:4])}...)")
    print(f"  消防站:     {len(fire_stations):4d} 个  (小类: 消防机关)")
    print(f"  避难场所:   {len(shelters):4d} 处  (容量 {shelters['capacity'].sum() if len(shelters) > 0 else 0:,} 人)")
    print(f"  地铁站:     {len(subway_stations):4d} 个  (小类: 地铁站)")
    print(f"  脆弱设施:   {len(vulnerable):4d} 处  (小类: {', '.join(VULNERABLE_SUBCATS)})")


def plot_poi_results(hospitals, fire_stations, shelters, subway_stations,
                     vulnerable, study_area, core, incident, fig_dir):
    """生成 POI 筛选结果可视化"""

    fig = plt.figure(figsize=(24, 20))
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.25)

    road_path = os.path.join(DIRS['road_network'], "roads_study_area.shp")
    has_roads = os.path.exists(road_path)
    roads = gpd.read_file(road_path) if has_roads else None

    def draw_basemap(ax, title):
        study_area.boundary.plot(ax=ax, color='#2196F3', linewidth=1, linestyle='--', alpha=0.4)
        core.plot(ax=ax, color='#FFF8E1', alpha=0.3, edgecolor='#E65100', linewidth=1.5)
        if has_roads:
            roads.plot(ax=ax, color='#E0E0E0', linewidth=0.2)
        incident.plot(ax=ax, color='red', marker='*', markersize=100, zorder=5, alpha=0.7)
        ax.set_title(title, fontsize=13, fontweight='bold')
        ax.set_xlabel('经度 (°E)', fontsize=9)
        ax.set_ylabel('纬度 (°N)', fontsize=9)
        ax.grid(True, alpha=0.15)

    # 图1: 全要素总览
    ax1 = fig.add_subplot(gs[0, 0:2])
    draw_basemap(ax1, '应急设施分布总览（严格小类筛选）')
    if len(shelters) > 0:
        shelters.plot(ax=ax1, color='#4CAF50', marker='s', markersize=15, alpha=0.5, zorder=6)
    if len(hospitals) > 0:
        hospitals.plot(ax=ax1, color='#D32F2F', marker='P', markersize=40, zorder=8,
                       edgecolor='white', linewidth=0.5)
    if len(fire_stations) > 0:
        fire_stations.plot(ax=ax1, color='#FF6F00', marker='^', markersize=60, zorder=9,
                           edgecolor='white', linewidth=0.5)
    if len(subway_stations) > 0:
        subway_stations.plot(ax=ax1, color='#1565C0', marker='o', markersize=25,
                             zorder=7, edgecolor='white', linewidth=0.5)
    legend_items = [
        Line2D([0],[0], marker='P', color='#D32F2F', linestyle='None', markersize=10,
               label=f'医院 ({len(hospitals)})'),
        Line2D([0],[0], marker='^', color='#FF6F00', linestyle='None', markersize=10,
               label=f'消防机关 ({len(fire_stations)})'),
        Line2D([0],[0], marker='s', color='#4CAF50', linestyle='None', markersize=8,
               label=f'避难场所 ({len(shelters)})'),
        Line2D([0],[0], marker='o', color='#1565C0', linestyle='None', markersize=8,
               label=f'地铁站 ({len(subway_stations)})'),
        Line2D([0],[0], marker='*', color='red', linestyle='None', markersize=12,
               label='事故点'),
    ]
    ax1.legend(handles=legend_items, loc='upper left', fontsize=9, framealpha=0.9)

    # 图2: 设施数量统计
    ax2 = fig.add_subplot(gs[0, 2])
    v_schools = len(vulnerable[vulnerable['type'] == '学校']) if 'type' in vulnerable.columns else 0
    v_kinder = len(vulnerable[vulnerable['type'] == '幼儿园']) if 'type' in vulnerable.columns else 0
    v_elderly = len(vulnerable[vulnerable['type'] == '养老/福利']) if 'type' in vulnerable.columns else 0
    categories = ['医院', '消防机关', '避难场所', '地铁站', '学校', '幼儿园', '养老/福利']
    counts = [len(hospitals), len(fire_stations), len(shelters), len(subway_stations),
              v_schools, v_kinder, v_elderly]
    colors_bar = ['#D32F2F', '#FF6F00', '#4CAF50', '#1565C0', '#7B1FA2', '#E91E63', '#795548']
    bars = ax2.barh(categories, counts, color=colors_bar, edgecolor='white')
    for bar, cnt in zip(bars, counts):
        ax2.text(bar.get_width() + max(counts) * 0.02, bar.get_y() + bar.get_height()/2,
                str(cnt), va='center', fontsize=10, fontweight='bold')
    ax2.set_title('研究范围内设施统计\n（严格小类筛选）', fontsize=13, fontweight='bold')
    ax2.set_xlabel('数量', fontsize=10)

    # 图3: 医院分布（含等级）
    ax3 = fig.add_subplot(gs[1, 0])
    draw_basemap(ax3, '医院分布与等级')
    level_colors = {'三甲': '#B71C1C', '三甲(推测)': '#D32F2F', '三乙': '#E53935',
                    '三级': '#EF5350', '二甲': '#FF7043', '二甲(推测)': '#FF8A65',
                    '二级': '#FFAB91', '基层': '#90A4AE', '待确认': '#CFD8DC', '未知': '#ECEFF1'}
    level_sizes = {'三甲': 80, '三甲(推测)': 80, '三乙': 60, '三级': 60,
                   '二甲': 45, '二甲(推测)': 45, '二级': 35, '基层': 20, '待确认': 25, '未知': 20}
    if len(hospitals) > 0:
        for level in hospitals['hospital_level'].unique():
            subset = hospitals[hospitals['hospital_level'] == level]
            color = level_colors.get(level, 'gray')
            size = level_sizes.get(level, 20)
            subset.plot(ax=ax3, color=color, marker='P', markersize=size,
                       label=f'{level} ({len(subset)})', zorder=8, edgecolor='white', linewidth=0.5)
        ax3.legend(loc='upper left', fontsize=8, title='医院等级')

    # 图4: 避难场所（按容量）
    ax4 = fig.add_subplot(gs[1, 1])
    draw_basemap(ax4, '避难场所分布（按容量）')
    if len(shelters) > 0:
        shelters.plot(ax=ax4, column='capacity', cmap='YlGn', markersize=30,
                      marker='s', legend=True, legend_kwds={'label': '容量 (人)', 'shrink': 0.6},
                      zorder=7, edgecolor='gray', linewidth=0.3)

    # 图5: 脆弱性设施
    ax5 = fig.add_subplot(gs[1, 2])
    draw_basemap(ax5, '脆弱性设施分布')
    type_markers = {'学校': ('D', '#7B1FA2', 20), '幼儿园': ('o', '#E91E63', 25),
                    '养老/福利': ('s', '#795548', 30)}
    if 'type' in vulnerable.columns:
        for vtype, (marker, color, size) in type_markers.items():
            subset = vulnerable[vulnerable['type'] == vtype]
            if len(subset) > 0:
                subset.plot(ax=ax5, color=color, marker=marker, markersize=size,
                           label=f'{vtype} ({len(subset)})', zorder=7,
                           edgecolor='white', linewidth=0.3)
        ax5.legend(loc='upper left', fontsize=9)

    fig.suptitle('Step 3: POI 筛选结果（严格小类版）', fontsize=18, fontweight='bold', y=1.01)
    fig_path = os.path.join(fig_dir, "step3_poi_filter.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  ✅ 图片已保存至 {fig_path}")


if __name__ == '__main__':
    main()
