"""
Step 7: 地铁网络构建
===================
功能：
  1. 从地铁站点 shp (metro_stops_with_opening_years.shp) 加载站点
  2. 从地铁线路 shp (metro_routes.shp) 加载线路
  3. 裁剪到研究范围并构建网络拓扑
  4. 赋站间运行时间
  5. 可视化

前置条件：先运行 step0
数据来源：config.py 中的 METRO_ROUTES_SHP 和 METRO_STOPS_SHP
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points, linemerge
import json
import pickle
import warnings
warnings.filterwarnings('ignore')
from config import *

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 地铁线路配色（可根据实际线路名自动分配）
LINE_COLORS = {
    '1号线': '#C23A30', '2号线': '#006098', '4号线': '#008B8D',
    '5号线': '#9B2793', '6号线': '#D09900', '7号线': '#F2C100',
    '8号线': '#009B6B', '9号线': '#8FC31F', '10号线': '#009BC0',
    '13号线': '#F9E500', '14号线': '#D4A76A', '15号线': '#6B3A73',
    '亦庄线': '#E91E63', '大兴线': '#4CAF50', '房山线': '#E66021',
    '昌平线': '#DE82B7', '大兴机场线': '#004DA0', 'S1线': '#B5A581',
    '燕房线': '#C85D16', '首都机场线': '#894E8A', '17号线': '#CBB99C',
    '19号线': '#C3AED2', '16号线': '#6BA539', '11号线': '#EE7733',
    '12号线': '#CC4411',
}

# 默认平均站间运行时间（分钟）
DEFAULT_AVG_TIME_MIN = 2.5

# 换乘步行时间（分钟）
TRANSFER_TIME_MIN = 4


def detect_field(gdf, candidates, description=""):
    """从候选列名列表中找到 GeoDataFrame 里实际存在的字段"""
    for c in candidates:
        if c in gdf.columns:
            return c
    print(f"  ⚠️ 未找到{description}字段，候选: {candidates}")
    print(f"     实际字段: {list(gdf.columns)}")
    return None


def _haversine_m(lon1, lat1, lon2, lat2):
    """Haversine 公式计算两点距离 (m)"""
    R = 6371000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam/2)**2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def get_line_color(line_name):
    """获取线路配色，支持模糊匹配"""
    name_str = str(line_name)
    # 直接匹配
    if name_str in LINE_COLORS:
        return LINE_COLORS[name_str]
    # 去掉常见前缀后匹配（如 "北京地铁1号线" → "1号线"）
    for prefix in ['北京地铁', '北京', '地铁']:
        stripped = name_str.replace(prefix, '')
        if stripped in LINE_COLORS:
            return LINE_COLORS[stripped]
    # 去掉方向后缀匹配（如 "1号线(苹果园-四惠东)" → "1号线"）
    base_name = name_str.split('(')[0].split('（')[0].strip()
    if base_name in LINE_COLORS:
        return LINE_COLORS[base_name]
    for prefix in ['北京地铁', '北京', '地铁']:
        stripped = base_name.replace(prefix, '')
        if stripped in LINE_COLORS:
            return LINE_COLORS[stripped]
    # 子串匹配
    for known_name, known_color in LINE_COLORS.items():
        if known_name in name_str or name_str in known_name:
            return known_color
    # 确定性伪随机颜色
    np.random.seed(hash(line_name) % 2**31)
    return '#{:06x}'.format(np.random.randint(0, 0xFFFFFF))


def main():
    print("=" * 60)
    print("Step 7: 地铁网络构建（基于地铁 SHP 数据）")
    print("=" * 60)

    out_dir = DIRS['subway']
    fig_dir = DIRS['figures']

    # ------------------------------------------------------------------
    # 1. 加载研究范围
    # ------------------------------------------------------------------
    print("\n[1/6] 加载研究范围...")
    study_area = gpd.read_file(os.path.join(DIRS['study_area'], "study_area_buffer.shp"))
    study_polygon = study_area.geometry.values[0]
    print(f"  研究范围加载完成")

    # ------------------------------------------------------------------
    # 2. 加载地铁站点 shp
    # ------------------------------------------------------------------
    print("\n[2/6] 加载地铁站点数据...")
    if not os.path.exists(METRO_STOPS_SHP):
        raise FileNotFoundError(f"地铁站点文件不存在: {METRO_STOPS_SHP}")

    stops_all = gpd.read_file(METRO_STOPS_SHP)
    print(f"  原始站点数: {len(stops_all)}")
    print(f"  坐标系: {stops_all.crs}")
    print(f"  字段: {list(stops_all.columns)}")

    # 预筛选北京（全国数据集时加速裁剪）
    if 'city_cn' in stops_all.columns:
        stops_all = stops_all[stops_all['city_cn'].str.contains('北京', na=False)]
        print(f"  筛选北京后站点数: {len(stops_all)}")
    elif 'city_code' in stops_all.columns:
        stops_all = stops_all[stops_all['city_code'].astype(str).str.startswith('110')]
        print(f"  筛选北京后站点数: {len(stops_all)}")

    # 统一坐标系
    if stops_all.crs and stops_all.crs != WGS84_CRS:
        stops_all = stops_all.to_crs(WGS84_CRS)
    elif stops_all.crs is None:
        print("  ⚠️ 无坐标系信息，假设为 WGS84")
        stops_all = stops_all.set_crs(WGS84_CRS)

    # 裁剪到研究范围
    stops = gpd.clip(stops_all, study_polygon)
    print(f"  研究范围内站点数: {len(stops)}")

    # 检测站名字段
    stop_name_col = detect_field(stops,
        ['stop_cn', 'stop_name', 'stop_nam', 'name', 'NAME', 'station_name',
         'station_n', 'stn_name', 'STOP_NAME', '站名', 'stat_name',
         'stop_name_cn', 'name_cn'],
        description="站名")

    # 检测线路名字段（站点表中）
    stop_line_col = detect_field(stops,
        ['route_cn', 'route_name', 'route_nam', 'line_name', 'line_nam',
         'line', 'LINE', 'ROUTE', 'route', '线路名', '线路', 'rte_name',
         'route_name_cn'],
        description="站点所属线路")

    if stop_name_col:
        print(f"  站名字段: {stop_name_col}")
        print(f"  站名示例: {stops[stop_name_col].head(10).tolist()}")
    if stop_line_col:
        print(f"  线路字段: {stop_line_col}")
        lines_in_stops = stops[stop_line_col].dropna().unique()
        print(f"  涉及线路: {list(lines_in_stops)}")

    # ------------------------------------------------------------------
    # 3. 加载地铁线路 shp
    # ------------------------------------------------------------------
    print("\n[3/6] 加载地铁线路数据...")
    if not os.path.exists(METRO_ROUTES_SHP):
        raise FileNotFoundError(f"地铁线路文件不存在: {METRO_ROUTES_SHP}")

    routes_all = gpd.read_file(METRO_ROUTES_SHP)
    print(f"  原始线路数: {len(routes_all)}")
    print(f"  坐标系: {routes_all.crs}")
    print(f"  字段: {list(routes_all.columns)}")

    # 预筛选北京（全国数据集时加速裁剪）
    if 'city_cn' in routes_all.columns:
        routes_all = routes_all[routes_all['city_cn'].str.contains('北京', na=False)]
        print(f"  筛选北京后线路数: {len(routes_all)}")
    elif 'city_code' in routes_all.columns:
        routes_all = routes_all[routes_all['city_code'].astype(str).str.startswith('110')]
        print(f"  筛选北京后线路数: {len(routes_all)}")

    # 统一坐标系
    if routes_all.crs and routes_all.crs != WGS84_CRS:
        routes_all = routes_all.to_crs(WGS84_CRS)
    elif routes_all.crs is None:
        routes_all = routes_all.set_crs(WGS84_CRS)

    # 裁剪到研究范围
    routes = gpd.clip(routes_all, study_polygon)
    routes = routes.explode(index_parts=False).reset_index(drop=True)
    print(f"  研究范围内线路段数: {len(routes)}")

    # 检测线路名字段
    route_name_col = detect_field(routes,
        ['route_cn', 'route_name', 'route_nam', 'name', 'NAME', 'line_name',
         'line_nam', 'line', 'LINE', 'ROUTE', '线路名', '线路', 'rte_name',
         'route_name_cn'],
        description="线路名")

    if route_name_col:
        route_names = routes[route_name_col].dropna().unique()
        print(f"  线路名字段: {route_name_col}")
        print(f"  涉及线路: {list(route_names)}")

    # ------------------------------------------------------------------
    # 4. 构建地铁网络拓扑
    # ------------------------------------------------------------------
    print("\n[4/6] 构建地铁网络拓扑...")

    # 线路名规范化：去方向后缀，使上下行合并为同一线路
    def normalize_line_name(name):
        """'北京地铁1号线(苹果园-四惠东)' → '1号线'"""
        s = str(name).split('(')[0].split('（')[0].strip()
        for prefix in ['北京地铁', '北京', '地铁']:
            s = s.replace(prefix, '')
        return s.strip()

    # 在站点和线路表中添加规范化列
    if stop_line_col and len(stops) > 0:
        stops['_line_norm'] = stops[stop_line_col].apply(normalize_line_name)
    if route_name_col and len(routes) > 0:
        routes['_line_norm'] = routes[route_name_col].apply(normalize_line_name)

    subway_G = nx.Graph()
    station_info = {}   # station_key -> {name, lon, lat, lines}
    line_edges = []      # [(u_key, v_key, line_name, color)]

    # --- 策略：按线路分组，将站点沿线路排序后相邻站连边 ---

    # 获取所有规范化线路名
    all_line_names = set()
    if stop_line_col and len(stops) > 0 and '_line_norm' in stops.columns:
        all_line_names.update(stops['_line_norm'].dropna().unique())
    if route_name_col and len(routes) > 0 and '_line_norm' in routes.columns:
        all_line_names.update(routes['_line_norm'].dropna().unique())

    # 去掉空字符串
    all_line_names.discard('')
    print(f"  全部线路（规范化后）: {sorted(all_line_names)}")

    if stop_line_col and stop_name_col:
        # ---- 主路径：站点表有线路字段，按线路分组处理 ----
        for line_name in sorted(all_line_names):
            # 用规范化名匹配站点（合并上下行方向）
            line_stops = stops[stops['_line_norm'] == line_name].copy()
            # 去重（上下行可能有重复站点）
            if stop_name_col in line_stops.columns:
                line_stops = line_stops.drop_duplicates(subset=[stop_name_col])
            if len(line_stops) < 2:
                continue

            color = get_line_color(line_name)

            # 获取对应的线路几何（合并所有方向）用于沿线排序站点
            line_geom = None
            if route_name_col and len(routes) > 0 and '_line_norm' in routes.columns:
                line_routes = routes[routes['_line_norm'] == line_name]
                if len(line_routes) > 0:
                    merged = linemerge(line_routes.geometry.tolist())
                    if merged.geom_type == 'LineString':
                        line_geom = merged
                    elif merged.geom_type == 'MultiLineString':
                        line_geom = max(merged.geoms, key=lambda g: g.length)

            # 排序站点：沿线路几何投影排序（若有），否则启发式排序
            if line_geom is not None:
                line_stops['_proj_dist'] = line_stops.geometry.apply(
                    lambda pt: line_geom.project(pt)
                )
                line_stops = line_stops.sort_values('_proj_dist').reset_index(drop=True)
            else:
                lon_range = line_stops.geometry.x.max() - line_stops.geometry.x.min()
                lat_range = line_stops.geometry.y.max() - line_stops.geometry.y.min()
                if lon_range >= lat_range:
                    line_stops = line_stops.assign(
                        _sort_key=line_stops.geometry.x
                    ).sort_values('_sort_key').reset_index(drop=True)
                else:
                    line_stops = line_stops.assign(
                        _sort_key=line_stops.geometry.y
                    ).sort_values('_sort_key').reset_index(drop=True)

            # 添加节点和边
            prev_key = None
            for _, row in line_stops.iterrows():
                sname = str(row[stop_name_col])
                lon, lat = row.geometry.x, row.geometry.y
                skey = sname  # 同名站点视为同一节点（换乘站）

                if skey not in station_info:
                    station_info[skey] = {
                        'name': sname, 'lon': lon, 'lat': lat, 'lines': []
                    }
                if line_name not in station_info[skey]['lines']:
                    station_info[skey]['lines'].append(line_name)

                subway_G.add_node(skey, lon=lon, lat=lat, name=sname)

                if prev_key is not None and prev_key != skey:
                    dist_m = _haversine_m(
                        station_info[prev_key]['lon'], station_info[prev_key]['lat'],
                        lon, lat
                    )
                    # 地铁平均速度约 35 km/h + 0.5min 停站
                    time_min = max(dist_m / 1000 / 35 * 60 + 0.5, DEFAULT_AVG_TIME_MIN)
                    time_s = time_min * 60

                    subway_G.add_edge(prev_key, skey,
                                      line=line_name,
                                      time_min=time_min,
                                      time_s=time_s,
                                      dist_m=dist_m,
                                      color=color)
                    line_edges.append((prev_key, skey, line_name, color))

                prev_key = skey

    elif stop_name_col and route_name_col and len(routes) > 0 and len(stops) > 0:
        # ---- 备选路径：站点无线路字段，通过空间距离关联 ----
        print("  ⚠️ 站点表缺少线路字段，通过空间距离匹配站点与线路...")
        stops_utm = stops.to_crs(UTM_CRS)

        for line_name in routes[route_name_col].dropna().unique():
            line_routes = routes[routes[route_name_col] == line_name]
            line_geom = line_routes.geometry.unary_union
            line_geom_utm = gpd.GeoSeries([line_geom], crs=WGS84_CRS).to_crs(UTM_CRS).values[0]

            dists = stops_utm.geometry.distance(line_geom_utm)
            nearby = stops[dists < 200].copy()  # 200m 容差

            if len(nearby) < 2:
                continue

            nearby['_proj_dist'] = nearby.geometry.apply(
                lambda pt: line_geom.project(pt)
            )
            nearby = nearby.sort_values('_proj_dist').reset_index(drop=True)

            color = get_line_color(line_name)

            prev_key = None
            for _, row in nearby.iterrows():
                sname = str(row[stop_name_col])
                lon, lat = row.geometry.x, row.geometry.y
                skey = sname

                if skey not in station_info:
                    station_info[skey] = {
                        'name': sname, 'lon': lon, 'lat': lat, 'lines': []
                    }
                if line_name not in station_info[skey]['lines']:
                    station_info[skey]['lines'].append(line_name)

                subway_G.add_node(skey, lon=lon, lat=lat, name=sname)

                if prev_key is not None and prev_key != skey:
                    dist_m = _haversine_m(
                        station_info[prev_key]['lon'], station_info[prev_key]['lat'],
                        lon, lat
                    )
                    time_min = max(dist_m / 1000 / 35 * 60 + 0.5, DEFAULT_AVG_TIME_MIN)
                    time_s = time_min * 60

                    subway_G.add_edge(prev_key, skey,
                                      line=line_name,
                                      time_min=time_min,
                                      time_s=time_s,
                                      dist_m=dist_m,
                                      color=color)
                    line_edges.append((prev_key, skey, line_name, color))

                prev_key = skey
    else:
        print("  ❌ 站点和线路字段均无法识别，无法构建网络拓扑")
        print("     请检查 shp 数据的字段名，并在代码中的 detect_field 候选列表中添加")

    # 识别换乘站（属于 ≥2 条线路的站点）
    transfer_stations = {k: v for k, v in station_info.items() if len(v['lines']) >= 2}
    print(f"\n  地铁站数: {subway_G.number_of_nodes()}")
    print(f"  连接边数: {subway_G.number_of_edges()}")
    print(f"  换乘站数: {len(transfer_stations)}")

    # 统计各线路
    line_count = {}
    for u, v, d in subway_G.edges(data=True):
        ln = d.get('line', '未知')
        line_count[ln] = line_count.get(ln, 0) + 1
    print(f"  覆盖线路:")
    for ln, cnt in sorted(line_count.items()):
        print(f"    {ln}: {cnt} 段")

    if transfer_stations:
        print(f"  换乘站:")
        for name, info in transfer_stations.items():
            print(f"    {name}: {' ↔ '.join(info['lines'])}")

    # ------------------------------------------------------------------
    # 5. 保存
    # ------------------------------------------------------------------
    print("\n[5/6] 保存...")

    # 保存站点
    if station_info:
        station_records = []
        for key, info in station_info.items():
            station_records.append({
                'name': info['name'],
                'lon': info['lon'],
                'lat': info['lat'],
                'lines': ','.join(info['lines']),
                'is_transfer': len(info['lines']) >= 2,
            })
        stations_df = pd.DataFrame(station_records)
        stations_gdf = gpd.GeoDataFrame(
            stations_df,
            geometry=gpd.points_from_xy(stations_df.lon, stations_df.lat),
            crs=WGS84_CRS
        )
        stations_gdf.to_file(os.path.join(out_dir, "subway_stations_network.shp"),
                             encoding='utf-8')

    # 保存边
    if line_edges:
        edge_records = []
        for u, v, line, color in line_edges:
            if u in station_info and v in station_info:
                geom = LineString([
                    (station_info[u]['lon'], station_info[u]['lat']),
                    (station_info[v]['lon'], station_info[v]['lat'])
                ])
                edge_data = subway_G[u][v]
                edge_records.append({
                    'from': u, 'to': v, 'line': line,
                    'time_min': round(edge_data.get('time_min', DEFAULT_AVG_TIME_MIN), 2),
                    'dist_m': round(edge_data.get('dist_m', 0), 0),
                    'geometry': geom
                })
        if edge_records:
            edges_gdf = gpd.GeoDataFrame(edge_records, crs=WGS84_CRS)
            edges_gdf.to_file(os.path.join(out_dir, "subway_lines_network.shp"),
                              encoding='utf-8')

    # 保存裁剪后的原始线路几何（可视化用）
    if len(routes) > 0:
        routes.to_file(os.path.join(out_dir, "subway_routes_clipped.shp"),
                       encoding='utf-8')

    # 保存 NetworkX 图
    with open(os.path.join(out_dir, "subway_graph.gpickle"), 'wb') as f:
        pickle.dump(subway_G, f)

    # 保存站点 CSV
    if station_info:
        stations_df.to_csv(os.path.join(out_dir, "subway_stations_list.csv"),
                           index=False, encoding='utf-8-sig')

    print(f"  ✅ 已保存至 {out_dir}")

    # ------------------------------------------------------------------
    # 6. 可视化
    # ------------------------------------------------------------------
    print("\n[6/6] 生成可视化...")
    plot_subway(subway_G, station_info, line_edges, routes, route_name_col, fig_dir)


def plot_subway(subway_G, station_info, line_edges, routes_gdf, route_name_col, fig_dir):
    """地铁网络可视化"""
    fig, axes = plt.subplots(1, 2, figsize=(20, 10))

    # 加载底图
    study_area = gpd.read_file(os.path.join(DIRS['study_area'], "study_area_buffer.shp"))
    core = gpd.read_file(os.path.join(DIRS['study_area'], "yizhuang_boundary.shp"))
    incident = gpd.read_file(os.path.join(DIRS['study_area'], "incident_point.shp"))
    road_path = os.path.join(DIRS['road_network'], "roads_study_area.shp")
    roads = gpd.read_file(road_path) if os.path.exists(road_path) else None

    # ===== 左图：地铁线路图（使用原始线路几何） =====
    ax1 = axes[0]
    study_area.boundary.plot(ax=ax1, color='#2196F3', linewidth=1, linestyle='--', alpha=0.4)
    core.boundary.plot(ax=ax1, color='#E65100', linewidth=1.5)
    if roads is not None:
        roads.plot(ax=ax1, color='#F5F5F5', linewidth=0.1)
    incident.plot(ax=ax1, color='red', marker='*', markersize=200, zorder=10)

    # 绘制原始线路几何（更平滑）
    drawn_lines = set()
    if route_name_col and len(routes_gdf) > 0:
        for line_name in routes_gdf[route_name_col].dropna().unique():
            color = get_line_color(line_name)
            subset = routes_gdf[routes_gdf[route_name_col] == line_name]
            subset.plot(ax=ax1, color=color, linewidth=3, alpha=0.8, zorder=5)
            drawn_lines.add((line_name, color))
    else:
        for u, v, line, color in line_edges:
            if u in station_info and v in station_info:
                ax1.plot([station_info[u]['lon'], station_info[v]['lon']],
                         [station_info[u]['lat'], station_info[v]['lat']],
                         color=color, linewidth=3, alpha=0.8, zorder=5)
                drawn_lines.add((line, color))

    # 绘制站点
    for name, info in station_info.items():
        is_transfer = len(info['lines']) >= 2
        size = 60 if is_transfer else 30
        edge_w = 1.5 if is_transfer else 0.8
        ax1.scatter(info['lon'], info['lat'], c='white', s=size, zorder=7,
                    edgecolor='black', linewidth=edge_w)
        if len(station_info) < 50 or is_transfer:
            ax1.annotate(name, (info['lon'], info['lat']),
                         fontsize=5, ha='left', va='bottom',
                         xytext=(3, 3), textcoords='offset points')

    # 图例
    legend_items = [Line2D([0], [0], color=c, linewidth=3, label=ln)
                    for ln, c in sorted(drawn_lines)]
    legend_items.append(Line2D([0], [0], marker='*', color='red',
                               linestyle='None', markersize=12, label='事故点'))
    legend_items.append(Line2D([0], [0], marker='o', color='white', markeredgecolor='black',
                               linestyle='None', markersize=8, markeredgewidth=1.5,
                               label='换乘站'))
    ax1.legend(handles=legend_items, loc='upper left', fontsize=8)
    ax1.set_title('地铁线路网络', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.2)

    # ===== 右图：网络拓扑图 =====
    ax2 = axes[1]
    if subway_G.number_of_nodes() > 0:
        pos = {n: (station_info[n]['lon'], station_info[n]['lat'])
               for n in subway_G.nodes() if n in station_info}
        edge_colors = [subway_G[u][v].get('color', 'gray')
                       for u, v in subway_G.edges() if u in pos and v in pos]
        edges_to_draw = [(u, v) for u, v in subway_G.edges() if u in pos and v in pos]

        nx.draw_networkx_edges(subway_G, pos, edgelist=edges_to_draw,
                               edge_color=edge_colors, width=2, ax=ax2, alpha=0.7)

        transfer_nodes = [n for n in subway_G.nodes()
                          if n in station_info and len(station_info[n]['lines']) >= 2]
        normal_nodes = [n for n in subway_G.nodes()
                        if n in station_info and len(station_info[n]['lines']) < 2]

        if normal_nodes:
            nx.draw_networkx_nodes(subway_G, pos, nodelist=normal_nodes,
                                   node_size=25, node_color='white',
                                   edgecolors='black', linewidths=0.8, ax=ax2)
        if transfer_nodes:
            nx.draw_networkx_nodes(subway_G, pos, nodelist=transfer_nodes,
                                   node_size=80, node_color='#FFD700',
                                   edgecolors='black', linewidths=1.5, ax=ax2)
        nx.draw_networkx_labels(subway_G, pos, font_size=4, ax=ax2)

    ax2.set_title('地铁网络拓扑', fontsize=14, fontweight='bold')
    ax2.axis('off')

    fig.suptitle('Step 7: 地铁网络构建结果', fontsize=18, fontweight='bold', y=1.02)
    fig_path = os.path.join(fig_dir, "step7_subway.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  ✅ 图片已保存至 {fig_path}")


if __name__ == '__main__':
    main()
