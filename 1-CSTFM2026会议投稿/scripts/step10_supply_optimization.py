"""
Step 10: 应急物资配送优化
=========================
功能：
  1. 构建"供应点—中转站—需求点"三层物流网络
  2. 需求包含两部分：
     a) 事故现场救援需求（核心区、隔离点、医院）
     b) 就地避难人口的物资需求（从 step11 输出读取）
  3. 货车—无人机协同：直送 + 接力两种模式
  4. 贪心构造 + 2-opt 局部搜索
  5. 多场景对比 + 敏感性分析

前置条件：step0 ~ step9, step11（step11 需先于 step10 运行）
  ⚠️ 运行顺序说明：step11 输出就地避难人口数据，step10 读取后
     生成对应的物资配送任务。若 step11 尚未运行，step10 会跳过
     就地避难需求，仅处理救援现场需求。
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from shapely.geometry import Point
import json
import copy
import warnings
warnings.filterwarnings('ignore')
from config import *

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ==================== 物资定义 ====================
SUPPLY_CATEGORIES = {
    'life_rescue': {
        'name': '生命救援类', 'name_en': 'Life Rescue',
        'items': ['防毒面具', '氧气瓶', '急救药品', '解毒剂'],
        'priority': 1, 'weight_per_unit_kg': 3.0,
        'time_window_min': 30, 'hard_window': True,
        'penalty_per_min': 1000, 'color': '#B71C1C',
    },
    'medical': {
        'name': '医疗支援类', 'name_en': 'Medical',
        'items': ['担架', '医疗设备', '血浆', '输液'],
        'priority': 2, 'weight_per_unit_kg': 8.0,
        'time_window_min': 60, 'hard_window': True,
        'penalty_per_min': 500, 'color': '#E53935',
    },
    'protection': {
        'name': '防护设备类', 'name_en': 'Protection',
        'items': ['防护服', '隔离带', '警示设备'],
        'priority': 3, 'weight_per_unit_kg': 5.0,
        'time_window_min': 120, 'hard_window': False,
        'penalty_per_min': 100, 'color': '#FF9800',
    },
    'basic': {
        'name': '基础保障类', 'name_en': 'Basic Supply',
        'items': ['饮用水', '食品', '帐篷', '照明设备'],
        'priority': 4, 'weight_per_unit_kg': 15.0,
        'time_window_min': 240, 'hard_window': False,
        'penalty_per_min': 10, 'color': '#FFC107',
    },
}

OBJ_W_MAKESPAN = 1.0
OBJ_W_PENALTY  = 1.0
OBJ_W_UNMET    = 10000.0

DRONE_SPEED_KMH  = 60
DRONE_MAX_KG     = 25
DRONE_MAX_RANGE_M = 15000
DRONE_LOAD_TIME_MIN = 5

# 就地避难物资需求率（每 1000 人）
SHELTER_SUPPLY_RATES = {
    'erpg2_k3': {'life_rescue': 0, 'medical': 5,  'protection': 200, 'basic': 100},
    'erpg1_k2': {'life_rescue': 0, 'medical': 3,  'protection': 100, 'basic': 80},
    'erpg1_k3': {'life_rescue': 0, 'medical': 0,  'protection': 50,  'basic': 60},
}

# 就地避难需求点空间偏移（相对事故点）
SHELTER_DEMAND_OFFSETS = {
    'erpg2': [
        ('ERPG2避难-北', 0, 0.010, 0.30),
        ('ERPG2避难-南', 0, -0.010, 0.30),
        ('ERPG2避难-东', 0.012, 0, 0.20),
        ('ERPG2避难-西', -0.012, 0, 0.20),
    ],
    'erpg1': [
        ('ERPG1避难-北', 0, 0.022, 0.20),
        ('ERPG1避难-南', 0, -0.022, 0.20),
        ('ERPG1避难-东北', 0.018, 0.015, 0.15),
        ('ERPG1避难-西北', -0.018, 0.015, 0.15),
        ('ERPG1避难-东南', 0.018, -0.015, 0.15),
        ('ERPG1避难-西南', -0.018, -0.015, 0.15),
    ],
}


class LogisticsNode:
    def __init__(self, name, lon, lat, node_type, capacity=None, demand=None, **kwargs):
        self.name = name
        self.lon = lon
        self.lat = lat
        self.type = node_type
        self.capacity = capacity or {}
        self.demand = demand or {}
        self.attrs = kwargs

    def euclidean_m(self, other):
        dlat = (other.lat - self.lat) * 110540
        dlon = (other.lon - self.lon) * 111320 * np.cos(np.radians(self.lat))
        return np.sqrt(dlat ** 2 + dlon ** 2)


class DeliveryTask:
    def __init__(self, task_id, demand_node, supply_cat, quantity, deadline_min):
        self.id = task_id
        self.demand = demand_node
        self.supply_cat = supply_cat
        self.quantity = quantity
        self.deadline = deadline_min
        self.priority = SUPPLY_CATEGORIES[supply_cat]['priority']
        self.penalty_rate = SUPPLY_CATEGORIES[supply_cat]['penalty_per_min']
        self.is_hard = SUPPLY_CATEGORIES[supply_cat].get('hard_window', False)


class Vehicle:
    def __init__(self, vid, vtype, speed_kmh, capacity_kg, base_node):
        self.id = vid
        self.type = vtype
        self.speed = speed_kmh
        self.capacity = capacity_kg
        self.base = base_node
        self.current_pos = base_node
        self.available_time = 0.0
        self.assigned_tasks = []


class DispatchPlan:
    def __init__(self, task, vehicle, supply_node, relay_node,
                 departure_time, arrival_time, route_type):
        self.task = task
        self.vehicle = vehicle
        self.supply_node = supply_node
        self.relay_node = relay_node
        self.departure_time = departure_time
        self.arrival_time = arrival_time
        self.route_type = route_type

    @property
    def penalty(self):
        if self.arrival_time <= self.task.deadline:
            return 0.0
        return (self.arrival_time - self.task.deadline) * self.task.penalty_rate

    def to_dict(self):
        return {
            'task_id': self.task.id, 'task_cat': self.task.supply_cat,
            'vehicle': self.vehicle.id, 'supply': self.supply_node.name,
            'relay': self.relay_node.name if self.relay_node else None,
            'demand': self.task.demand.name,
            'departure': round(self.departure_time, 2),
            'arrival': round(self.arrival_time, 2),
            'deadline': self.task.deadline,
            'penalty': round(self.penalty, 2),
            'route_type': self.route_type,
        }


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


def get_travel_time_min(router, node_a, node_b, speed_kmh=40):
    if router is not None:
        return router.travel_time_min(node_a.lon, node_a.lat,
                                       node_b.lon, node_b.lat)
    else:
        dist_m = node_a.euclidean_m(node_b)
        return (dist_m / 1000) / speed_kmh * 60


# ==================== 就地避难物资需求 ====================

def load_shelter_demand_nodes(inc_lon, inc_lat):
    """
    从 step11 输出的 evacuation_results.json 读取就地避难人口，
    转化为物资配送需求点。若 step11 尚未运行则返回空列表。
    """
    evac_path = os.path.join(DIRS['evac_opt'], "evacuation_results.json")
    if not os.path.exists(evac_path):
        print("  ℹ️ step11 尚未运行，跳过就地避难物资需求")
        return []

    try:
        with open(evac_path, 'r', encoding='utf-8') as f:
            evac_data = json.load(f)
        shelter_pops = evac_data.get('shelter_in_place', {}).get(
            'shelter_in_place_population', {})
    except Exception as e:
        print(f"  ⚠️ 读取 step11 输出失败: {e}")
        return []

    if not shelter_pops:
        print("  ℹ️ 无就地避难人口数据")
        return []

    # 计算各区域物资需求总量
    zone_demands = {}
    for zone in ['erpg2', 'erpg1']:
        zp = shelter_pops.get(zone, {})
        demand = {'life_rescue': 0, 'medical': 0, 'protection': 0, 'basic': 0}
        for k_str, pop in zp.items():
            rate_key = f'{zone}_k{k_str}'
            rates = SHELTER_SUPPLY_RATES.get(rate_key, {})
            for cat, rate_per_1000 in rates.items():
                demand[cat] += int(int(pop) / 1000 * rate_per_1000)
        zone_demands[zone] = demand

    # 生成需求点
    nodes = []
    for zone, offsets in SHELTER_DEMAND_OFFSETS.items():
        zd = zone_demands.get(zone, {})
        if sum(zd.values()) == 0:
            continue
        for name, dx, dy, share in offsets:
            node_demand = {cat: int(qty * share) for cat, qty in zd.items() if qty > 0}
            node_demand = {cat: qty for cat, qty in node_demand.items() if qty > 0}
            if not node_demand:
                continue
            nodes.append(LogisticsNode(
                name=name, lon=inc_lon + dx, lat=inc_lat + dy,
                node_type='demand', demand=node_demand,
            ))

    print(f"  ✅ 从就地避难人口生成 {len(nodes)} 个物资需求点")
    for n in nodes:
        total = sum(n.demand.values())
        print(f"    {n.name}: 总需求 {total} 单位")
    return nodes


# ==================== 物流网络构建 ====================

def build_logistics_network(scenario_json):
    print("  构建物流网络...")
    hospitals = gpd.read_file(os.path.join(DIRS['poi'], "hospitals.shp"))
    fire_stations = gpd.read_file(os.path.join(DIRS['poi'], "fire_stations.shp"))
    shelters = gpd.read_file(os.path.join(DIRS['poi'], "shelters.shp"))

    inc_lon = scenario_json['incident']['location']['lon']
    inc_lat = scenario_json['incident']['location']['lat']
    inc_point = Point(inc_lon, inc_lat)

    # ---- 供应点 ----
    supply_nodes = []
    for _, row in fire_stations.iterrows():
        dist = inc_point.distance(row.geometry) * 111000
        if 1000 < dist < 15000:
            supply_nodes.append(LogisticsNode(
                name=str(row.get('name', f'消防站_{len(supply_nodes)}')),
                lon=row.geometry.x, lat=row.geometry.y, node_type='supply',
                capacity={'life_rescue': 50, 'medical': 30, 'protection': 100, 'basic': 200},
            ))
            if len(supply_nodes) >= 8:
                break
    for wh in scenario_json.get('resources', {}).get('emergency_warehouses', []):
        supply_nodes.append(LogisticsNode(
            name=wh['name'], lon=wh['lon'], lat=wh['lat'], node_type='supply',
            capacity={'life_rescue': 200, 'medical': 100, 'protection': 500, 'basic': 1000},
        ))
    print(f"    供应点: {len(supply_nodes)}")

    # ---- 中转站 ----
    relay_nodes = []
    for _, row in shelters.iterrows():
        dist = inc_point.distance(row.geometry) * 111000
        if 2000 < dist < 6000:
            cap = row.get('capacity', 1000)
            if isinstance(cap, (int, float)) and cap > 2000:
                relay_nodes.append(LogisticsNode(
                    name=str(row.get('name', f'中转_{len(relay_nodes)}')),
                    lon=row.geometry.x, lat=row.geometry.y, node_type='relay',
                ))
                if len(relay_nodes) >= 6:
                    break
    if len(relay_nodes) < 3:
        for _, row in shelters.iterrows():
            dist = inc_point.distance(row.geometry) * 111000
            if 1500 < dist < 8000 and len(relay_nodes) < 5:
                relay_nodes.append(LogisticsNode(
                    name=str(row.get('name', f'中转_{len(relay_nodes)}')),
                    lon=row.geometry.x, lat=row.geometry.y, node_type='relay',
                ))
    print(f"    中转站: {len(relay_nodes)}")

    # ---- 需求点 A：事故现场救援需求 ----
    demand_nodes = []
    demand_nodes.append(LogisticsNode(
        name='事故核心区', lon=inc_lon, lat=inc_lat + 0.005,
        node_type='demand',
        demand={'life_rescue': 100, 'medical': 50, 'protection': 200, 'basic': 100},
    ))
    offsets = [(0.01, 0), (-0.01, 0), (0, 0.01), (0, -0.01)]
    dirs_cn = ['东侧隔离点', '西侧隔离点', '北侧隔离点', '南侧隔离点']
    for (dx, dy), dname in zip(offsets, dirs_cn):
        demand_nodes.append(LogisticsNode(
            name=dname, lon=inc_lon + dx, lat=inc_lat + dy,
            node_type='demand',
            demand={'life_rescue': 20, 'medical': 30, 'protection': 80, 'basic': 150},
        ))
    for _, row in hospitals.iterrows():
        dist = inc_point.distance(row.geometry) * 111000
        if 2000 < dist < 10000:
            demand_nodes.append(LogisticsNode(
                name=str(row.get('name', '医院')),
                lon=row.geometry.x, lat=row.geometry.y, node_type='demand',
                demand={'medical': 20, 'basic': 30},
            ))
            if len(demand_nodes) >= 15:
                break

    n_rescue = len(demand_nodes)
    print(f"    救援现场需求点: {n_rescue}")

    # ---- 需求点 B：就地避难人口物资需求 ----
    shelter_nodes = load_shelter_demand_nodes(inc_lon, inc_lat)
    demand_nodes.extend(shelter_nodes)
    print(f"    就地避难需求点: {len(shelter_nodes)}")
    print(f"    总需求点: {len(demand_nodes)}")

    return supply_nodes, relay_nodes, demand_nodes


# ==================== 目标函数 ====================

def compute_objective(schedule, all_tasks):
    if not schedule:
        return float('inf'), 0, 0, len(all_tasks)
    makespan = max(p.arrival_time for p in schedule)
    total_penalty = sum(p.penalty for p in schedule)
    served_ids = {p.task.id for p in schedule}
    unmet_count = sum(1 for t in all_tasks if t.id not in served_ids)
    obj = (OBJ_W_MAKESPAN * makespan + OBJ_W_PENALTY * total_penalty +
           OBJ_W_UNMET * unmet_count)
    return obj, makespan, total_penalty, unmet_count


# ==================== 贪心构造 ====================

def greedy_construct(supply_nodes, relay_nodes, demand_nodes,
                     trucks, drones, all_tasks, router,
                     use_drones=True, use_relay=True):
    tasks_sorted = sorted(all_tasks, key=lambda t: (t.priority, t.deadline))
    schedule = []
    supply_remaining = {s.name: dict(s.capacity) for s in supply_nodes}
    vehicles = list(trucks)
    if use_drones:
        vehicles += list(drones)
    veh_available = {v.id: 0.0 for v in vehicles}
    veh_pos = {v.id: v.base for v in vehicles}

    for task in tasks_sorted:
        best_plan = None
        best_arrival = float('inf')

        for v in vehicles:
            if v.type == 'drone' and not use_drones:
                continue
            if v.type == 'drone':
                unit_w = SUPPLY_CATEGORIES[task.supply_cat]['weight_per_unit_kg']
                if task.quantity * unit_w > v.capacity:
                    continue
            avail_t = veh_available[v.id]
            cur_pos = veh_pos[v.id]

            # 直送
            for s in supply_nodes:
                rem = supply_remaining[s.name].get(task.supply_cat, 0)
                if rem <= 0:
                    continue
                t_to_supply = get_travel_time_min(router, cur_pos, s, v.speed)
                t_to_demand = get_travel_time_min(router, s, task.demand, v.speed)
                arrival = max(avail_t, 0) + t_to_supply + t_to_demand
                if arrival < best_arrival:
                    best_arrival = arrival
                    best_plan = DispatchPlan(
                        task=task, vehicle=v, supply_node=s, relay_node=None,
                        departure_time=max(avail_t, 0),
                        arrival_time=arrival, route_type='direct')

            # 接力
            if use_relay and v.type == 'truck':
                for r in relay_nodes:
                    for s in supply_nodes:
                        rem = supply_remaining[s.name].get(task.supply_cat, 0)
                        if rem <= 0:
                            continue
                        t1 = max(avail_t, 0) + get_travel_time_min(router, cur_pos, s, v.speed)
                        t2 = t1 + get_travel_time_min(router, s, r, v.speed)
                        drone_dist_m = r.euclidean_m(task.demand)
                        if drone_dist_m > DRONE_MAX_RANGE_M:
                            continue
                        drone_t = (drone_dist_m / 1000) / DRONE_SPEED_KMH * 60
                        arrival = t2 + DRONE_LOAD_TIME_MIN + drone_t
                        if arrival < best_arrival:
                            best_arrival = arrival
                            best_plan = DispatchPlan(
                                task=task, vehicle=v, supply_node=s, relay_node=r,
                                departure_time=max(avail_t, 0),
                                arrival_time=arrival, route_type='relay')

        if best_plan is not None:
            v = best_plan.vehicle
            s = best_plan.supply_node
            veh_available[v.id] = best_plan.arrival_time + 5
            veh_pos[v.id] = (best_plan.task.demand
                             if best_plan.route_type == 'direct'
                             else best_plan.relay_node)
            supply_remaining[s.name][task.supply_cat] = max(
                0, supply_remaining[s.name].get(task.supply_cat, 0) - task.quantity)
            schedule.append(best_plan)

    return schedule


# ==================== 局部搜索 ====================

def local_search_2opt(schedule, all_tasks, supply_nodes, router, max_iter=200):
    if len(schedule) < 2:
        return schedule
    best_obj, _, _, _ = compute_objective(schedule, all_tasks)
    improved = True
    iteration = 0
    while improved and iteration < max_iter:
        improved = False
        iteration += 1
        for i in range(len(schedule)):
            for j in range(i + 1, len(schedule)):
                if schedule[i].vehicle.type != schedule[j].vehicle.type:
                    continue
                new_schedule = list(schedule)
                pi, pj = new_schedule[i], new_schedule[j]
                new_i = _reassign(pi, pj.vehicle, supply_nodes, router)
                new_j = _reassign(pj, pi.vehicle, supply_nodes, router)
                if new_i is None or new_j is None:
                    continue
                new_schedule[i] = new_i
                new_schedule[j] = new_j
                new_obj, _, _, _ = compute_objective(new_schedule, all_tasks)
                if new_obj < best_obj - 0.01:
                    schedule = new_schedule
                    best_obj = new_obj
                    improved = True
                    break
            if improved:
                break
    return schedule


def _reassign(plan, new_vehicle, supply_nodes, router):
    try:
        t_to_supply = get_travel_time_min(router, new_vehicle.base,
                                           plan.supply_node, new_vehicle.speed)
        t_to_demand = get_travel_time_min(router, plan.supply_node,
                                           plan.task.demand, new_vehicle.speed)
        arrival = t_to_supply + t_to_demand
        return DispatchPlan(
            task=plan.task, vehicle=new_vehicle,
            supply_node=plan.supply_node, relay_node=plan.relay_node,
            departure_time=0, arrival_time=arrival, route_type=plan.route_type)
    except Exception:
        return None


# ==================== 求解 ====================

def solve_supply_optimization(supply_nodes, relay_nodes, demand_nodes,
                               n_trucks, n_drones, all_tasks, router,
                               use_drones=True, use_relay=True,
                               do_local_search=True):
    trucks = []
    for i in range(n_trucks):
        base = supply_nodes[i % len(supply_nodes)] if supply_nodes else demand_nodes[0]
        trucks.append(Vehicle(f'T{i}', 'truck', speed_kmh=40, capacity_kg=2000, base_node=base))
    drones = []
    for i in range(n_drones):
        base = relay_nodes[i % max(1, len(relay_nodes))] if relay_nodes else (
            supply_nodes[0] if supply_nodes else demand_nodes[0])
        drones.append(Vehicle(f'D{i}', 'drone', speed_kmh=DRONE_SPEED_KMH,
                              capacity_kg=DRONE_MAX_KG, base_node=base))

    schedule = greedy_construct(supply_nodes, relay_nodes, demand_nodes,
                                trucks, drones, all_tasks, router,
                                use_drones=use_drones, use_relay=use_relay)
    if do_local_search and len(schedule) > 1:
        schedule = local_search_2opt(schedule, all_tasks, supply_nodes, router)
    obj, makespan, total_penalty, unmet = compute_objective(schedule, all_tasks)
    return schedule, obj, makespan, total_penalty, unmet


def summarize_results(schedule, all_tasks, label):
    obj, makespan, penalty, unmet = compute_objective(schedule, all_tasks)
    completion_times = [p.arrival_time for p in schedule]
    avg_time = np.mean(completion_times) if completion_times else 0

    by_cat = {}
    for cat_key, cat_info in SUPPLY_CATEGORIES.items():
        cat_plans = [p for p in schedule if p.task.supply_cat == cat_key]
        cat_times = [p.arrival_time for p in cat_plans]
        deadline = cat_info['time_window_min']
        on_time = sum(1 for t in cat_times if t <= deadline)
        by_cat[cat_key] = {
            'task_count': len(cat_plans),
            'avg_time_min': float(np.mean(cat_times)) if cat_times else 0,
            'max_time_min': float(np.max(cat_times)) if cat_times else 0,
            'on_time_count': on_time,
            'on_time_rate': on_time / max(1, len(cat_plans)),
            'deadline_min': deadline,
        }

    return {
        'label': label,
        'total_tasks': len(all_tasks),
        'completed_tasks': len(schedule),
        'unmet_tasks': unmet,
        'objective_value': float(obj),
        'makespan_min': float(makespan),
        'avg_delivery_time_min': float(avg_time),
        'total_penalty': float(penalty),
        'by_category': by_cat,
        'route_types': {
            'direct': sum(1 for p in schedule if p.route_type == 'direct'),
            'relay': sum(1 for p in schedule if p.route_type == 'relay'),
        },
    }


# ==================== 主函数 ====================

def run_optimization():
    print("=" * 60)
    print("Step 10: 应急物资配送优化")
    print("=" * 60)

    out_dir = DIRS['supply_opt']
    fig_dir = DIRS['figures']

    with open(os.path.join(DIRS['integrated'], "scenario_params.json"), 'r', encoding='utf-8') as f:
        scenario = json.load(f)

    print("\n[1/6] 加载路网行程时间计算器...")
    router = load_router(incident_mode=True)

    print("\n[2/6] 构建物流网络...")
    supply_nodes, relay_nodes, demand_nodes = build_logistics_network(scenario)

    print("\n[3/6] 生成配送任务...")
    all_tasks = []
    tid = 0
    for d_node in demand_nodes:
        for cat_key, cat_info in SUPPLY_CATEGORIES.items():
            qty = d_node.demand.get(cat_key, 0)
            if qty > 0:
                all_tasks.append(DeliveryTask(
                    task_id=tid, demand_node=d_node, supply_cat=cat_key,
                    quantity=qty, deadline_min=cat_info['time_window_min'],
                ))
                tid += 1

    print(f"  总任务数: {len(all_tasks)}")
    for cat_key, cat_info in SUPPLY_CATEGORIES.items():
        ct = [t for t in all_tasks if t.supply_cat == cat_key]
        print(f"    {cat_info['name']}: {len(ct)} 任务, 总需求 {sum(t.quantity for t in ct)}")

    print("\n[4/6] 运行多场景对比...")
    drone_cfg = scenario.get('resources', {}).get('drones', {'count': 10})
    truck_cfg = scenario.get('resources', {}).get('trucks', {'count': 20})

    scenario_configs = {
        'truck_only':        {'trucks': truck_cfg['count'], 'drones': 0,
                              'use_drones': False, 'use_relay': False,
                              'label': '纯货车'},
        'coordinated':       {'trucks': truck_cfg['count'], 'drones': drone_cfg['count'],
                              'use_drones': True, 'use_relay': True,
                              'label': '货车-无人机协同'},
        'drone_only':        {'trucks': 0, 'drones': drone_cfg['count'],
                              'use_drones': True, 'use_relay': False,
                              'label': '纯无人机'},
        'coord_more_drones': {'trucks': truck_cfg['count'], 'drones': drone_cfg['count'] * 2,
                              'use_drones': True, 'use_relay': True,
                              'label': '协同(加倍无人机)'},
    }

    all_results = {}
    for sc_name, sc in scenario_configs.items():
        print(f"\n  --- {sc['label']} ---")
        tasks_c = copy.deepcopy(all_tasks)
        supply_c = copy.deepcopy(supply_nodes)
        relay_c = copy.deepcopy(relay_nodes)
        schedule, obj, makespan, penalty, unmet = solve_supply_optimization(
            supply_c, relay_c, demand_nodes,
            n_trucks=sc['trucks'], n_drones=sc['drones'],
            all_tasks=tasks_c, router=router,
            use_drones=sc['use_drones'], use_relay=sc['use_relay'],
        )
        result = summarize_results(schedule, tasks_c, sc['label'])
        result['config'] = sc
        all_results[sc_name] = result
        print(f"    完成: {result['completed_tasks']}/{result['total_tasks']} 任务")
        print(f"    Makespan: {makespan:.1f} min, 惩罚: {penalty:,.0f}, 未满足: {unmet}")

    print("\n[5/6] 敏感性分析（无人机数量）...")
    sensitivity_results = []
    for n_drones in [0, 5, 10, 15, 20, 30, 40]:
        tasks_c = copy.deepcopy(all_tasks)
        supply_c = copy.deepcopy(supply_nodes)
        relay_c = copy.deepcopy(relay_nodes)
        sch, obj_val, mk, pen, unm = solve_supply_optimization(
            supply_c, relay_c, demand_nodes,
            n_trucks=truck_cfg['count'], n_drones=n_drones,
            all_tasks=tasks_c, router=router,
            use_drones=(n_drones > 0), use_relay=(n_drones > 0),
            do_local_search=False,
        )
        life_plans = [p for p in sch if p.task.supply_cat == 'life_rescue']
        life_on_time = (sum(1 for p in life_plans if p.arrival_time <= 30)
                        / max(1, len(life_plans)))
        sensitivity_results.append({
            'n_drones': n_drones, 'makespan': float(mk),
            'avg_time': float(np.mean([p.arrival_time for p in sch])) if sch else 0,
            'penalty': float(pen), 'objective': float(obj_val),
            'life_rescue_on_time_rate': float(life_on_time),
            'completed': len(sch),
        })
        print(f"    无人机={n_drones:2d}: makespan={mk:.1f}min, 准时率={life_on_time:.1%}")

    print("\n[6/6] 保存结果...")
    output_json = {
        'logistics_network': {
            'supply_nodes': [{'name': n.name, 'lon': n.lon, 'lat': n.lat} for n in supply_nodes],
            'relay_nodes': [{'name': n.name, 'lon': n.lon, 'lat': n.lat} for n in relay_nodes],
            'demand_nodes': [{'name': n.name, 'lon': n.lon, 'lat': n.lat,
                              'type': n.type} for n in demand_nodes],
        },
        'supply_categories': {k: {kk: vv for kk, vv in v.items() if kk != 'color'}
                              for k, v in SUPPLY_CATEGORIES.items()},
        'objective_weights': {
            'makespan': OBJ_W_MAKESPAN, 'penalty': OBJ_W_PENALTY, 'unmet': OBJ_W_UNMET},
        'scenario_comparison': all_results,
        'sensitivity_drone_count': sensitivity_results,
        'uses_road_network': router is not None,
        'includes_shelter_demands': any(n.type == 'demand' and '避难' in n.name
                                        for n in demand_nodes),
    }
    json_path = os.path.join(out_dir, "supply_optimization_results.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_json, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✅ JSON: {json_path}")

    print("\n" + "=" * 60)
    print("Step 10 完成")
    print("=" * 60)


def main():
    run_optimization()


if __name__ == '__main__':
    main()
