"""
network_router.py — 路网行程时间计算工具
=========================================
供 step10 / step11 共用。
功能：
  1. 加载 step2 构建的路网 NetworkX 图
  2. 将任意 (lon, lat) 映射到路网最近节点（KDTree 加速）
  3. 基于 Dijkstra 计算路网最短行程时间
  4. 支持事故场景（路段封闭 + BPR 拥堵）
  5. 缓存已计算结果，避免重复计算

使用方法：
    from network_router import NetworkRouter
    router = NetworkRouter(graph_path, incident_mode=True,
                           incident_lon=116.506, incident_lat=39.795)
    t_min = router.travel_time_min(lon1, lat1, lon2, lat2)
"""

import os
import pickle
import numpy as np
import networkx as nx
from scipy.spatial import cKDTree

# BPR 参数（与 config.py 一致）
BPR_ALPHA = 0.15
BPR_BETA = 4.0


class NetworkRouter:
    """基于路网图的行程时间计算器"""

    def __init__(self, graph_path, incident_mode=False,
                 incident_lon=None, incident_lat=None,
                 closure_radius_m=1000, congestion_radius_m=3000):
        """
        Parameters
        ----------
        graph_path : str
            road_network_graph.gpickle 的路径
        incident_mode : bool
            是否启用事故模式（封闭 + 拥堵）
        incident_lon, incident_lat : float
            事故点 WGS84 坐标（incident_mode=True 时必填）
        closure_radius_m : float
            道路封闭半径 (m)
        congestion_radius_m : float
            BPR 拥堵效应半径 (m)
        """
        print(f"  [NetworkRouter] 加载路网图: {graph_path}")
        with open(graph_path, 'rb') as f:
            self.G = pickle.load(f)
        print(f"    节点: {self.G.number_of_nodes()}, 边: {self.G.number_of_edges()}")

        # 构建节点数组 + KDTree
        self.node_list = list(self.G.nodes())
        self.node_arr = np.array(self.node_list)  # shape (N, 2), 列=[lon, lat]
        self.kdtree = cKDTree(self.node_arr)

        # 默认权重字段
        self.weight_field = 'freeflow_time_s'

        # 事故模式
        if incident_mode and incident_lon is not None:
            self._apply_incident(incident_lon, incident_lat,
                                 closure_radius_m, congestion_radius_m)
            self.weight_field = 'incident_time_s'

        # 缓存：(node_o, node_d) -> time_seconds
        self._cache = {}
        # 缓存：(lon, lat) -> nearest_graph_node
        self._node_cache = {}

    # ----------------------------------------------------------------
    # 事故路段封闭 + 拥堵
    # ----------------------------------------------------------------
    def _apply_incident(self, inc_lon, inc_lat, closure_m, congestion_m):
        """模拟事故：封闭路段 + BPR 拥堵"""
        closure_deg = closure_m / 111000
        congestion_deg = congestion_m / 111000

        edges_to_remove = []
        for u, v, data in self.G.edges(data=True):
            mid_lon = (u[0] + v[0]) / 2
            mid_lat = (u[1] + v[1]) / 2
            dist_deg = ((mid_lon - inc_lon)**2 + (mid_lat - inc_lat)**2)**0.5

            if dist_deg < closure_deg:
                edges_to_remove.append((u, v))
            elif dist_deg < congestion_deg:
                base_time = data.get('freeflow_time_s', 60)
                congestion_factor = 1 + BPR_ALPHA * (0.8 ** BPR_BETA)
                proximity = (congestion_deg - dist_deg) / congestion_deg
                data['incident_time_s'] = base_time * congestion_factor * (1 + proximity)
            else:
                data['incident_time_s'] = data.get('freeflow_time_s', 60)

        self.G.remove_edges_from(edges_to_remove)
        print(f"    [事故模式] 封闭 {len(edges_to_remove)} 条路段, "
              f"剩余 {self.G.number_of_edges()}")

    # ----------------------------------------------------------------
    # 最近路网节点映射
    # ----------------------------------------------------------------
    def nearest_node(self, lon, lat):
        """将 (lon, lat) 映射到路网最近节点"""
        key = (round(lon, 6), round(lat, 6))
        if key in self._node_cache:
            return self._node_cache[key]
        _, idx = self.kdtree.query([lon, lat])
        node = self.node_list[idx]
        self._node_cache[key] = node
        return node

    # ----------------------------------------------------------------
    # 行程时间计算
    # ----------------------------------------------------------------
    def travel_time_sec(self, lon1, lat1, lon2, lat2):
        """
        计算两点间的路网最短行程时间（秒）。
        如果路网不可达，返回基于欧氏距离的估算值（30 km/h）作为兜底。
        """
        node_o = self.nearest_node(lon1, lat1)
        node_d = self.nearest_node(lon2, lat2)

        if node_o == node_d:
            return 0.0

        cache_key = (node_o, node_d)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            t = nx.dijkstra_path_length(self.G, node_o, node_d,
                                        weight=self.weight_field)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            # 不可达时用欧氏距离兜底（30 km/h）
            dist_m = self._euclidean_m(lon1, lat1, lon2, lat2)
            t = dist_m / (30 / 3.6)

        self._cache[cache_key] = t
        return t

    def travel_time_min(self, lon1, lat1, lon2, lat2):
        """计算两点间的路网最短行程时间（分钟）"""
        return self.travel_time_sec(lon1, lat1, lon2, lat2) / 60.0

    # ----------------------------------------------------------------
    # 批量预计算
    # ----------------------------------------------------------------
    def precompute_matrix(self, points):
        """
        批量预计算多点之间的行程时间矩阵 (分钟)。

        Parameters
        ----------
        points : list of (name, lon, lat)

        Returns
        -------
        dict : {(name_i, name_j): time_min}
        """
        print(f"    [NetworkRouter] 预计算 {len(points)}×{len(points)} 行程时间矩阵...")
        # 映射到路网节点 + 批量 Dijkstra
        mapped = {}
        for name, lon, lat in points:
            mapped[name] = self.nearest_node(lon, lat)

        matrix = {}
        names = [p[0] for p in points]
        for i, name_o in enumerate(names):
            node_o = mapped[name_o]
            try:
                lengths = nx.single_source_dijkstra_path_length(
                    self.G, node_o, weight=self.weight_field)
            except nx.NodeNotFound:
                lengths = {}

            for j, name_d in enumerate(names):
                if i == j:
                    matrix[(name_o, name_d)] = 0.0
                    continue
                node_d = mapped[name_d]
                if node_d in lengths:
                    matrix[(name_o, name_d)] = lengths[node_d] / 60.0
                else:
                    # 不可达兜底
                    lon_o, lat_o = points[i][1], points[i][2]
                    lon_d, lat_d = points[j][1], points[j][2]
                    dist_m = self._euclidean_m(lon_o, lat_o, lon_d, lat_d)
                    matrix[(name_o, name_d)] = dist_m / (30 / 3.6) / 60.0

        print(f"    完成: {len(matrix)} 对")
        return matrix

    # ----------------------------------------------------------------
    # 工具
    # ----------------------------------------------------------------
    @staticmethod
    def _euclidean_m(lon1, lat1, lon2, lat2):
        """欧氏距离近似 (m)"""
        dlat = (lat2 - lat1) * 110540
        dlon = (lon2 - lon1) * 111320 * np.cos(np.radians((lat1 + lat2) / 2))
        return np.sqrt(dlat**2 + dlon**2)

    def euclidean_m(self, lon1, lat1, lon2, lat2):
        return self._euclidean_m(lon1, lat1, lon2, lat2)
