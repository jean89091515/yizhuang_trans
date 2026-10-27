"""
Step 6: 行程时间矩阵估算
=========================
功能：
  1. 加载路网图和关键节点（医院、消防站、避难所、事故点）
  2. 将关键节点映射到路网最近节点
  3. 计算自由流行程时间矩阵
  4. 模拟事故情景（路段封闭）下的行程时间矩阵
  5. 可视化

前置条件：先运行 step0, step2, step3
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
import pickle
from shapely.geometry import Point, LineString
import warnings
warnings.filterwarnings('ignore')
from config import *

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def find_nearest_node(G, lon, lat):
    """找到图中离给定坐标最近的节点"""
    min_dist = float('inf')
    nearest = None
    for node in G.nodes():
        d = (node[0] - lon) ** 2 + (node[1] - lat) ** 2
        if d < min_dist:
            min_dist = d
            nearest = node
    return nearest


def find_nearest_node_fast(nodes_arr, lon, lat):
    """向量化版本的最近节点查找"""
    dists = (nodes_arr[:, 0] - lon) ** 2 + (nodes_arr[:, 1] - lat) ** 2
    return int(np.argmin(dists))


def load_key_facilities():
    """加载关键设施节点"""
    facilities = {}

    # 事故点
    incident = gpd.read_file(os.path.join(DIRS['study_area'], "incident_point.shp"))
    facilities['事故点_太平桥'] = {
        'lon': incident.geometry.x.values[0],
        'lat': incident.geometry.y.values[0],
        'type': 'incident'
    }

    # 医院
    hosp_path = os.path.join(DIRS['poi'], "hospitals.shp")
    if os.path.exists(hosp_path):
        hospitals = gpd.read_file(hosp_path)
        for i, row in hospitals.iterrows():
            name = str(row.get('name', f'医院_{i}'))[:20]
            facilities[f'医院_{name}'] = {
                'lon': row.geometry.x, 'lat': row.geometry.y, 'type': 'hospital'
            }

    # 消防站
    fire_path = os.path.join(DIRS['poi'], "fire_stations.shp")
    if os.path.exists(fire_path):
        fires = gpd.read_file(fire_path)
        for i, row in fires.iterrows():
            name = str(row.get('name', f'消防站_{i}'))[:20]
            facilities[f'消防_{name}'] = {
                'lon': row.geometry.x, 'lat': row.geometry.y, 'type': 'fire_station'
            }

    # 避难所（只取容量前 20 的）
    shelter_path = os.path.join(DIRS['poi'], "shelters.shp")
    if os.path.exists(shelter_path):
        shelters = gpd.read_file(shelter_path)
        if 'capacity' in shelters.columns:
            shelters = shelters.nlargest(20, 'capacity')
        else:
            shelters = shelters.head(20)
        for i, row in shelters.iterrows():
            name = str(row.get('name', f'避难所_{i}'))[:20]
            facilities[f'避难_{name}'] = {
                'lon': row.geometry.x, 'lat': row.geometry.y, 'type': 'shelter'
            }

    return facilities


def compute_time_matrix(G, facilities, nodes_arr, node_list, weight='freeflow_time_s'):
    """计算关键节点间的行程时间矩阵"""
    names = list(facilities.keys())
    n = len(names)
    matrix = np.full((n, n), np.inf)

    # 映射到最近路网节点
    mapped_nodes = {}
    for name, info in facilities.items():
        idx = find_nearest_node_fast(nodes_arr, info['lon'], info['lat'])
        mapped_nodes[name] = node_list[idx]

    # 计算最短路径
    for i, name_o in enumerate(names):
        node_o = mapped_nodes[name_o]
        try:
            lengths = nx.single_source_dijkstra_path_length(G, node_o, weight=weight)
            for j, name_d in enumerate(names):
                if i != j:
                    node_d = mapped_nodes[name_d]
                    if node_d in lengths:
                        matrix[i, j] = lengths[node_d]
        except nx.NetworkXError:
            pass

    matrix_df = pd.DataFrame(matrix, index=names, columns=names)
    return matrix_df, mapped_nodes


def simulate_incident(G, incident_lon, incident_lat, nodes_arr, node_list,
                      closure_radius_m=1000):
    """模拟事故：封闭事故点周边路段"""
    G_incident = G.copy()

    # 找到事故点附近的节点
    incident_node = node_list[find_nearest_node_fast(nodes_arr, incident_lon, incident_lat)]

    # 封闭附近路段（距离事故点 closure_radius_m 以内的边）
    edges_to_remove = []
    # 简化：以经纬度差异估算（0.01度 ≈ 1km）
    radius_deg = closure_radius_m / 111000
    for u, v, data in G_incident.edges(data=True):
        mid_lon = (u[0] + v[0]) / 2
        mid_lat = (u[1] + v[1]) / 2
        dist = ((mid_lon - incident_lon)**2 + (mid_lat - incident_lat)**2) ** 0.5
        if dist < radius_deg:
            edges_to_remove.append((u, v))

    # 周边路段加重（拥堵效应）
    congestion_radius = radius_deg * 3
    for u, v, data in G_incident.edges(data=True):
        mid_lon = (u[0] + v[0]) / 2
        mid_lat = (u[1] + v[1]) / 2
        dist = ((mid_lon - incident_lon)**2 + (mid_lat - incident_lat)**2) ** 0.5
        if dist < congestion_radius:
            # BPR 拥堵效应：假设流量达容量 80%
            congestion_factor = 1 + BPR_ALPHA * (0.8 ** BPR_BETA)
            data['incident_time_s'] = data.get('freeflow_time_s', 60) * congestion_factor * (1 + (congestion_radius - dist) / congestion_radius)
        else:
            data['incident_time_s'] = data.get('freeflow_time_s', 60)

    G_incident.remove_edges_from(edges_to_remove)
    print(f"  封闭路段数: {len(edges_to_remove)}")
    print(f"  剩余路段数: {G_incident.number_of_edges()}")

    return G_incident, edges_to_remove


def main():
    print("=" * 60)
    print("Step 6: 行程时间矩阵估算")
    print("=" * 60)

    out_dir = DIRS['travel_time']
    fig_dir = DIRS['figures']

    # 加载路网图
    print("\n[1/5] 加载路网图...")
    graph_path = os.path.join(DIRS['road_network'], "road_network_graph.gpickle")
    if not os.path.exists(graph_path):
        raise FileNotFoundError(f"路网图不存在: {graph_path}\n请先运行 step2_road_network.py")
    with open(graph_path, 'rb') as f:
        G = pickle.load(f)
    print(f"  节点: {G.number_of_nodes()}, 边: {G.number_of_edges()}")

    # 预处理节点数组（加速查找）
    node_list = list(G.nodes())
    nodes_arr = np.array(node_list)

    # 加载关键设施
    print("\n[2/5] 加载关键设施...")
    facilities = load_key_facilities()
    print(f"  关键节点数: {len(facilities)}")
    type_counts = {}
    for info in facilities.values():
        t = info['type']
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, c in type_counts.items():
        print(f"    {t}: {c}")

    # 自由流行程时间矩阵
    print("\n[3/5] 计算自由流行程时间矩阵...")
    matrix_free, mapped = compute_time_matrix(G, facilities, nodes_arr, node_list)
    # 转换为分钟
    matrix_free_min = matrix_free / 60
    matrix_free_min.to_csv(os.path.join(out_dir, "time_matrix_freeflow_min.csv"),
                           encoding='utf-8-sig')
    print(f"  ✅ 自由流矩阵已保存")

    # 打印事故点到各设施的时间
    incident_name = [n for n in facilities if '事故' in n][0]
    print(f"\n  从事故点出发的自由流行程时间（分钟）:")
    incident_times = matrix_free_min.loc[incident_name].sort_values()
    for name, t in incident_times.head(15).items():
        if t < np.inf and name != incident_name:
            print(f"    → {name}: {t:.1f} min")

    # 事故情景
    print("\n[4/5] 模拟事故情景...")
    G_incident, closed_edges = simulate_incident(
        G, INCIDENT_LON, INCIDENT_LAT, nodes_arr, node_list,
        closure_radius_m=1000
    )

    matrix_inc, _ = compute_time_matrix(G_incident, facilities, nodes_arr, node_list,
                                         weight='incident_time_s')
    matrix_inc_min = matrix_inc / 60
    matrix_inc_min.to_csv(os.path.join(out_dir, "time_matrix_incident_min.csv"),
                          encoding='utf-8-sig')

    # 计算影响
    print(f"\n  事故后行程时间变化:")
    inc_times = matrix_inc_min.loc[incident_name].sort_values()
    for name in incident_times.head(10).index:
        if name != incident_name:
            t_free = matrix_free_min.loc[incident_name, name]
            t_inc = matrix_inc_min.loc[incident_name, name]
            if t_free < np.inf and t_inc < np.inf:
                pct = (t_inc - t_free) / t_free * 100 if t_free > 0 else 0
                print(f"    {name}: {t_free:.1f} → {t_inc:.1f} min ({pct:+.0f}%)")
            elif t_inc == np.inf and t_free < np.inf:
                print(f"    {name}: {t_free:.1f} → 不可达 ❌")

    # 可视化
    print("\n[5/5] 生成可视化...")
    plot_travel_time(matrix_free_min, matrix_inc_min, facilities, mapped,
                     closed_edges, fig_dir)

    print("\n" + "=" * 60)
    print("Step 6 完成")
    print("=" * 60)


def plot_travel_time(matrix_free, matrix_inc, facilities, mapped, closed_edges, fig_dir):
    """行程时间可视化"""

    fig = plt.figure(figsize=(24, 12))
    gs = fig.add_gridspec(1, 3, wspace=0.3)

    # 加载底图
    study_area = gpd.read_file(os.path.join(DIRS['study_area'], "study_area_buffer.shp"))
    core = gpd.read_file(os.path.join(DIRS['study_area'], "yizhuang_boundary.shp"))
    road_path = os.path.join(DIRS['road_network'], "roads_study_area.shp")
    roads = gpd.read_file(road_path) if os.path.exists(road_path) else None

    # ===== 图1: 自由流热力图 =====
    ax1 = fig.add_subplot(gs[0, 0])
    n = min(20, len(matrix_free))
    # 只显示有效值
    display = matrix_free.iloc[:n, :n].replace(np.inf, np.nan)
    im = ax1.imshow(display.values, cmap='RdYlGn_r', aspect='auto')
    ax1.set_xticks(range(n))
    ax1.set_yticks(range(n))
    short_names = [name[:8] for name in display.index[:n]]
    ax1.set_xticklabels(short_names, rotation=90, fontsize=6)
    ax1.set_yticklabels(short_names, fontsize=6)
    plt.colorbar(im, ax=ax1, shrink=0.6, label='行程时间 (min)')
    ax1.set_title('自由流行程时间矩阵', fontsize=13, fontweight='bold')

    # ===== 图2: 事故情景对比 =====
    ax2 = fig.add_subplot(gs[0, 1])
    # 时间增加比率
    ratio = (matrix_inc.iloc[:n, :n] / matrix_free.iloc[:n, :n]).replace([np.inf, np.nan], 0)
    im2 = ax2.imshow(ratio.values, cmap='Reds', aspect='auto', vmin=1, vmax=3)
    ax2.set_xticks(range(n))
    ax2.set_yticks(range(n))
    ax2.set_xticklabels(short_names, rotation=90, fontsize=6)
    ax2.set_yticklabels(short_names, fontsize=6)
    plt.colorbar(im2, ax=ax2, shrink=0.6, label='时间增加倍率')
    ax2.set_title('事故后行程时间增加倍率', fontsize=13, fontweight='bold')

    # ===== 图3: 空间可达性 =====
    ax3 = fig.add_subplot(gs[0, 2])
    study_area.boundary.plot(ax=ax3, color='#2196F3', linewidth=1, linestyle='--', alpha=0.4)
    core.boundary.plot(ax=ax3, color='#E65100', linewidth=1.5)
    if roads is not None:
        roads.plot(ax=ax3, color='#E0E0E0', linewidth=0.15)

    # 绘制封闭路段
    for u, v in closed_edges[:200]:  # 限制绘制数量
        ax3.plot([u[0], v[0]], [u[1], v[1]], color='red', linewidth=2, alpha=0.6)

    # 绘制关键节点
    type_styles = {
        'incident': ('*', 'red', 200),
        'hospital': ('P', '#D32F2F', 60),
        'fire_station': ('^', '#FF6F00', 60),
        'shelter': ('s', '#4CAF50', 40),
    }
    for name, info in facilities.items():
        marker, color, size = type_styles.get(info['type'], ('o', 'gray', 20))
        ax3.scatter(info['lon'], info['lat'], marker=marker, c=color,
                   s=size, zorder=10, edgecolor='white', linewidth=0.5)

    # 图例
    legend_items = [
        mpatches.Patch(color='red', alpha=0.6, label='封闭路段'),
        plt.Line2D([0],[0], marker='*', color='red', linestyle='None', markersize=12, label='事故点'),
        plt.Line2D([0],[0], marker='P', color='#D32F2F', linestyle='None', markersize=8, label='医院'),
        plt.Line2D([0],[0], marker='^', color='#FF6F00', linestyle='None', markersize=8, label='消防站'),
        plt.Line2D([0],[0], marker='s', color='#4CAF50', linestyle='None', markersize=8, label='避难场所'),
    ]
    ax3.legend(handles=legend_items, loc='upper left', fontsize=8)
    ax3.set_title('事故路段封闭与设施分布', fontsize=13, fontweight='bold')
    ax3.grid(True, alpha=0.2)

    fig.suptitle('Step 6: 行程时间矩阵估算结果', fontsize=18, fontweight='bold', y=1.02)
    fig_path = os.path.join(fig_dir, "step6_travel_time.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  ✅ 图片已保存至 {fig_path}")


if __name__ == '__main__':
    main()
