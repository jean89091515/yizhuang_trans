"""
Step 2: 路网数据处理
===================
功能：
  1. 读取 OSM 路网 shapefile
  2. 裁剪到研究范围
  3. 筛选车行道路 & 赋属性（限速、通行能力）
  4. 计算路段长度和自由流行程时间
  5. 构建 NetworkX 拓扑图
  6. 检查连通性
  7. 多角度可视化
  
前置条件：先运行 step0_study_area.py 生成研究范围文件
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.lines import Line2D
import networkx as nx
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points
import pickle
import warnings
warnings.filterwarnings('ignore')
from config import *

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 道路等级配色
ROAD_COLORS = {
    'motorway': '#E53935', 'motorway_link': '#EF5350',
    'trunk': '#FF6F00',    'trunk_link': '#FFA000',
    'primary': '#F9A825',  'primary_link': '#FDD835',
    'secondary': '#43A047','secondary_link': '#66BB6A',
    'tertiary': '#1E88E5', 'tertiary_link': '#42A5F5',
    'residential': '#90A4AE', 'unclassified': '#B0BEC5',
    'service': '#CFD8DC',  'living_street': '#ECEFF1',
}

ROAD_WIDTHS = {
    'motorway': 2.5, 'motorway_link': 1.5,
    'trunk': 2.0,    'trunk_link': 1.2,
    'primary': 1.8,  'primary_link': 1.0,
    'secondary': 1.5,'secondary_link': 0.8,
    'tertiary': 1.2, 'tertiary_link': 0.6,
    'residential': 0.8, 'unclassified': 0.6,
    'service': 0.4,  'living_street': 0.4,
}

# 道路中文名称
ROAD_NAMES_CN = {
    'motorway': '高速公路', 'motorway_link': '高速匝道',
    'trunk': '快速路',      'trunk_link': '快速路匝道',
    'primary': '主干路',    'primary_link': '主干路匝道',
    'secondary': '次干路',  'secondary_link': '次干路匝道',
    'tertiary': '支路',     'tertiary_link': '支路匝道',
    'residential': '住宅区道路', 'unclassified': '未分类道路',
    'service': '服务道路',  'living_street': '生活街区',
}


def load_study_area():
    """加载 step0 生成的研究范围"""
    sa_path = os.path.join(DIRS['study_area'], "study_area_buffer.shp")
    core_path = os.path.join(DIRS['study_area'], "yizhuang_boundary.shp")
    incident_path = os.path.join(DIRS['study_area'], "incident_point.shp")

    if not os.path.exists(sa_path):
        raise FileNotFoundError(f"找不到研究范围文件: {sa_path}\n请先运行 step0_study_area.py")

    study_area = gpd.read_file(sa_path)
    core = gpd.read_file(core_path)
    incident = gpd.read_file(incident_path)
    return study_area, core, incident


def process_road_network():
    print("=" * 60)
    print("Step 2: 路网数据处理")
    print("=" * 60)

    study_area, core, incident = load_study_area()
    study_polygon = study_area.geometry.values[0]
    out_dir = DIRS['road_network']
    fig_dir = DIRS['figures']

    # ------------------------------------------------------------------
    # 1. 读取 OSM 路网
    # ------------------------------------------------------------------
    print("\n[1/6] 读取 OSM 路网...")
    roads_all = gpd.read_file(OSM_ROAD_SHP)
    print(f"  全北京道路总数: {len(roads_all)}")
    print(f"  坐标系: {roads_all.crs}")
    print(f"  道路类型: {roads_all['fclass'].nunique()} 种")

    # ------------------------------------------------------------------
    # 2. 裁剪到研究范围
    # ------------------------------------------------------------------
    print("\n[2/6] 裁剪到研究范围...")
    roads_clip = gpd.clip(roads_all, study_polygon)
    # 裁剪可能产生 MultiLineString（路段被研究范围边界切断），拆成单条 LineString
    roads_clip = roads_clip.explode(index_parts=False).reset_index(drop=True)
    # 去除可能出现的空几何或非线类型
    roads_clip = roads_clip[roads_clip.geometry.type == 'LineString']
    print(f"  裁剪后道路数: {len(roads_clip)}")

    # ------------------------------------------------------------------
    # 3. 筛选车行道路 & 赋属性
    # ------------------------------------------------------------------
    print("\n[3/6] 筛选车行道路并赋属性...")
    roads = roads_clip[roads_clip['fclass'].isin(VEHICLE_ROAD_CLASSES)].copy()
    print(f"  车行道路数: {len(roads)}")

    # 赋默认限速
    roads['speed_default'] = roads['fclass'].map(SPEED_MAP)
    # maxspeed 字段可能含非数值或为 0，尝试转换
    roads['maxspeed_num'] = pd.to_numeric(roads['maxspeed'], errors='coerce')
    # 关键：既要替换 NaN，也要替换 0（OSM 中 0 表示未填写）
    roads['maxspeed_num'] = roads['maxspeed_num'].replace(0, np.nan)
    roads['speed_final'] = roads['maxspeed_num'].fillna(roads['speed_default'])
    # 最终兜底：如果仍有 0 或 NaN，用 30 km/h
    roads['speed_final'] = roads['speed_final'].replace(0, 30).fillna(30)

    # 赋通行能力
    roads['capacity'] = roads['fclass'].map(CAPACITY_MAP)

    # 道路中文名称
    roads['fclass_cn'] = roads['fclass'].map(ROAD_NAMES_CN)

    # ------------------------------------------------------------------
    # 4. 计算路段长度和自由流行程时间
    # ------------------------------------------------------------------
    print("\n[4/6] 计算路段长度和行程时间...")
    roads_utm = roads.to_crs(UTM_CRS)
    roads['length_m'] = roads_utm.geometry.length
    # 安全计算：避免除以零
    roads['freeflow_time_s'] = roads['length_m'] / (roads['speed_final'].clip(lower=5) / 3.6)
    roads['freeflow_time_min'] = roads['freeflow_time_s'] / 60

    print(f"  路网总长度: {roads['length_m'].sum() / 1000:.1f} km")
    print(f"  平均路段长度: {roads['length_m'].mean():.1f} m")

    # 统计各类道路
    road_stats = roads.groupby('fclass').agg(
        count=('fclass', 'size'),
        total_km=('length_m', lambda x: x.sum() / 1000),
        avg_speed=('speed_final', 'mean')
    ).round(1)
    road_stats = road_stats.sort_values('total_km', ascending=False)
    print("\n  各类道路统计:")
    for idx, row in road_stats.iterrows():
        cn = ROAD_NAMES_CN.get(idx, idx)
        print(f"    {cn:8s} ({idx:16s}): {row['count']:5.0f} 条, "
              f"{row['total_km']:7.1f} km, 均速 {row['avg_speed']:.0f} km/h")

    # ------------------------------------------------------------------
    # 5. 构建 NetworkX 图
    # ------------------------------------------------------------------
    print("\n[5/6] 构建路网拓扑图...")
    G = nx.DiGraph()

    for idx, row in roads.iterrows():
        coords = list(row.geometry.coords)
        start_node = coords[0]
        end_node = coords[-1]

        # 添加边属性
        edge_attrs = {
            'osm_id': row.get('osm_id', ''),
            'fclass': row['fclass'],
            'name': row.get('name', ''),
            'length_m': row['length_m'],
            'speed_kmh': row['speed_final'],
            'freeflow_time_s': row['freeflow_time_s'],
            'capacity': row['capacity'],
            'geometry': row.geometry,
        }

        # 添加正向边
        G.add_edge(start_node, end_node, **edge_attrs)

        # 非单向道路添加反向边
        oneway = str(row.get('oneway', 'F')).upper()
        if oneway not in ['T', 'YES', '1', 'TRUE']:
            G.add_edge(end_node, start_node, **edge_attrs)

    print(f"  节点数: {G.number_of_nodes()}")
    print(f"  边数: {G.number_of_edges()}")

    # 连通性检查
    if nx.is_weakly_connected(G):
        print("  ✅ 图是弱连通的")
    else:
        components = list(nx.weakly_connected_components(G))
        largest = max(components, key=len)
        print(f"  ⚠️ 图有 {len(components)} 个弱连通分量")
        print(f"  最大分量包含 {len(largest)} 个节点 ({len(largest)/G.number_of_nodes()*100:.1f}%)")
        # 保留最大连通分量
        G = G.subgraph(largest).copy()
        print(f"  已保留最大连通分量")

    # ------------------------------------------------------------------
    # 6. 保存
    # ------------------------------------------------------------------
    print("\n[6/6] 保存文件...")
    roads.to_file(os.path.join(out_dir, "roads_study_area.shp"), encoding='utf-8')
    road_stats.to_csv(os.path.join(out_dir, "road_statistics.csv"), encoding='utf-8-sig')

    # 保存 NetworkX 图
    graph_path = os.path.join(out_dir, "road_network_graph.gpickle")
    with open(graph_path, 'wb') as f:
        pickle.dump(G, f)

    print(f"  ✅ 路网已保存至 {out_dir}")

    # ------------------------------------------------------------------
    # 可视化
    # ------------------------------------------------------------------
    print("\n正在生成可视化...")
    plot_road_network(roads, study_area, core, incident, road_stats, fig_dir)

    return roads, G


def plot_road_network(roads, study_area, core, incident, road_stats, fig_dir):
    """生成路网可视化图表"""

    # ✅ 每次绘图前重设中文字体（防止被其他 step 的 rcParams 覆盖）
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['axes.unicode_minus'] = False

    fig = plt.figure(figsize=(24, 18))
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3)

    # ===== 图1: 按道路等级着色 =====
    ax1 = fig.add_subplot(gs[0, 0:2])
    study_area.boundary.plot(ax=ax1, color='#2196F3', linewidth=1.5, linestyle='--', alpha=0.6)
    core.plot(ax=ax1, color='#FF9800', alpha=0.15, edgecolor='#E65100', linewidth=1.5)

    # 按道路等级分层绘制（低等级先画，高等级后画）
    draw_order = ['service', 'living_street', 'unclassified', 'residential',
                  'tertiary_link', 'tertiary', 'secondary_link', 'secondary',
                  'primary_link', 'primary', 'trunk_link', 'trunk',
                  'motorway_link', 'motorway']
    for fclass in draw_order:
        subset = roads[roads['fclass'] == fclass]
        if len(subset) > 0:
            color = ROAD_COLORS.get(fclass, 'gray')
            width = ROAD_WIDTHS.get(fclass, 0.5)
            subset.plot(ax=ax1, color=color, linewidth=width)

    incident.plot(ax=ax1, color='red', marker='*', markersize=200, zorder=10)

    # 图例
    legend_items = []
    for fclass in ['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'residential']:
        legend_items.append(
            Line2D([0], [0], color=ROAD_COLORS[fclass],
                   linewidth=ROAD_WIDTHS[fclass] * 2,
                   label=f"{ROAD_NAMES_CN[fclass]}")
        )
    legend_items.append(Line2D([0], [0], marker='*', color='red', linestyle='None',
                               markersize=15, label='事故点'))
    ax1.legend(handles=legend_items, loc='upper left', fontsize=9, framealpha=0.9)
    ax1.set_title('研究范围路网 — 按道路等级着色', fontsize=14, fontweight='bold')
    ax1.set_xlabel('经度 (°E)')
    ax1.set_ylabel('纬度 (°N)')
    ax1.grid(True, alpha=0.2)

    # ===== 图2: 道路等级统计饼图 =====
    ax2 = fig.add_subplot(gs[0, 2])
    top_classes = road_stats.head(8)
    other_km = road_stats.iloc[8:]['total_km'].sum() if len(road_stats) > 8 else 0

    labels = [ROAD_NAMES_CN.get(idx, idx) for idx in top_classes.index]
    sizes = top_classes['total_km'].values.tolist()
    if other_km > 0:
        labels.append('其他')
        sizes.append(other_km)

    colors_pie = [ROAD_COLORS.get(idx, '#BDBDBD') for idx in top_classes.index]
    if other_km > 0:
        colors_pie.append('#BDBDBD')

    wedges, texts, autotexts = ax2.pie(sizes, labels=labels, colors=colors_pie,
                                        autopct='%1.1f%%', pctdistance=0.8,
                                        textprops={'fontsize': 8})
    for text in autotexts:
        text.set_fontsize(7)
    ax2.set_title(f'道路类型构成\n(总长 {sum(sizes):.0f} km)', fontsize=13, fontweight='bold')

    # ===== 图3: 限速分布热力图 =====
    ax3 = fig.add_subplot(gs[1, 0])
    study_area.boundary.plot(ax=ax3, color='#2196F3', linewidth=1, linestyle='--', alpha=0.4)
    core.plot(ax=ax3, color='none', edgecolor='#E65100', linewidth=1.5)

    speed_colors = {20: '#1A237E', 30: '#1565C0', 40: '#2E7D32',
                    50: '#F9A825', 60: '#FF6F00', 80: '#E65100', 100: '#B71C1C'}

    for speed in sorted(speed_colors.keys()):
        subset = roads[roads['speed_final'] == speed]
        if len(subset) > 0:
            subset.plot(ax=ax3, color=speed_colors[speed], linewidth=0.6)

    legend_speed = [Line2D([0], [0], color=c, linewidth=2, label=f'{s} km/h')
                    for s, c in sorted(speed_colors.items())]
    ax3.legend(handles=legend_speed, loc='upper left', fontsize=8, title='限速')
    ax3.set_title('路网限速分布', fontsize=13, fontweight='bold')
    ax3.set_xlabel('经度 (°E)')
    ax3.set_ylabel('纬度 (°N)')
    ax3.grid(True, alpha=0.2)

    # ===== 图4: 路段长度分布直方图 =====
    ax4 = fig.add_subplot(gs[1, 1])
    lengths = roads['length_m'].values
    lengths_clip = lengths[lengths < 2000]  # 截断显示
    ax4.hist(lengths_clip, bins=50, color='#1976D2', alpha=0.7, edgecolor='white')
    ax4.axvline(np.median(lengths), color='red', linestyle='--', linewidth=1.5,
                label=f'中位数 {np.median(lengths):.0f} m')
    ax4.axvline(np.mean(lengths), color='orange', linestyle='--', linewidth=1.5,
                label=f'均值 {np.mean(lengths):.0f} m')
    ax4.set_xlabel('路段长度 (m)', fontsize=11)
    ax4.set_ylabel('路段数量', fontsize=11)
    ax4.set_title('路段长度分布', fontsize=13, fontweight='bold')
    ax4.legend(fontsize=9)

    # ===== 图5: 通行能力分布 =====
    ax5 = fig.add_subplot(gs[1, 2])
    cap_stats = roads.groupby('fclass')['capacity'].first().sort_values(ascending=True)
    cap_labels = [ROAD_NAMES_CN.get(f, f) for f in cap_stats.index]
    cap_colors = [ROAD_COLORS.get(f, 'gray') for f in cap_stats.index]
    bars = ax5.barh(cap_labels, cap_stats.values, color=cap_colors, edgecolor='white')
    ax5.set_xlabel('单向通行能力 (pcu/h)', fontsize=11)
    ax5.set_title('各等级道路通行能力', fontsize=13, fontweight='bold')
    for bar, val in zip(bars, cap_stats.values):
        ax5.text(val + 50, bar.get_y() + bar.get_height() / 2,
                f'{val:.0f}', va='center', fontsize=8)

    fig.suptitle('Step 2: 路网数据处理结果', fontsize=18, fontweight='bold', y=1.01)
    fig_path = os.path.join(fig_dir, "step2_road_network.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  ✅ 图片已保存至 {fig_path}")


def main():
    return process_road_network()


if __name__ == '__main__':
    roads, G = main()