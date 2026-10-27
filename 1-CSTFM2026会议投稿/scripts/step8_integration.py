"""
Step 8: 数据整合与检验
=====================
功能：
  1. 加载所有步骤的产出
  2. 空间一致性检验（全要素叠加图）
  3. 数据完整性检查
  4. 生成最终汇总报告
  5. 创建事故场景参数文件
  6. 综合可视化大图

前置条件：先运行 step0 ~ step7（至少完成 step0, 2, 3）
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
import json
import shutil
import warnings
warnings.filterwarnings('ignore')
from config import *

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def check_file(path, name):
    """检查文件是否存在并返回状态"""
    if os.path.exists(path):
        size = os.path.getsize(path)
        return True, f"✅ {name}: {size/1024:.0f} KB"
    else:
        return False, f"❌ {name}: 文件不存在"


def main():
    print("=" * 60)
    print("Step 8: 数据整合与检验")
    print("=" * 60)

    out_dir = DIRS['integrated']
    fig_dir = DIRS['figures']
    report = []

    # ==================================================================
    # 1. 文件完整性检查
    # ==================================================================
    print("\n[1/5] 文件完整性检查...")
    files_to_check = {
        '研究范围': os.path.join(DIRS['study_area'], "study_area_buffer.shp"),
        '核心边界': os.path.join(DIRS['study_area'], "yizhuang_boundary.shp"),
        '事故点': os.path.join(DIRS['study_area'], "incident_point.shp"),
        '路网': os.path.join(DIRS['road_network'], "roads_study_area.shp"),
        '路网图': os.path.join(DIRS['road_network'], "road_network_graph.gpickle"),
        '医院': os.path.join(DIRS['poi'], "hospitals.shp"),
        '消防站': os.path.join(DIRS['poi'], "fire_stations.shp"),
        '避难所': os.path.join(DIRS['poi'], "shelters.shp"),
        '地铁站': os.path.join(DIRS['poi'], "subway_stations.shp"),
        '脆弱设施': os.path.join(DIRS['poi'], "vulnerable_facilities.shp"),
        '人口数据': os.path.join(DIRS['population'], "block_pop_study_area.shp"),
        '年龄结构': os.path.join(DIRS['population'], "age_structure_by_district.csv"),
        'OD天数据': os.path.join(DIRS['od_data'], "od_day_study_area.csv"),
        'OD小时数据': os.path.join(DIRS['od_data'], "od_hour_study_area.csv"),
        '通勤数据': os.path.join(DIRS['commute'], "commute_study_area.csv"),
        '行程时间(自由流)': os.path.join(DIRS['travel_time'], "time_matrix_freeflow_min.csv"),
        '行程时间(事故)': os.path.join(DIRS['travel_time'], "time_matrix_incident_min.csv"),
        '地铁网络': os.path.join(DIRS['subway'], "subway_graph.gpickle"),
    }

    completed = 0
    for name, path in files_to_check.items():
        exists, msg = check_file(path, name)
        print(f"  {msg}")
        report.append(msg)
        if exists:
            completed += 1

    total = len(files_to_check)
    print(f"\n  完成度: {completed}/{total} ({completed/total*100:.0f}%)")

    # ==================================================================
    # 2. 数据量统计
    # ==================================================================
    print("\n[2/5] 数据量统计...")
    stats = {}

    # 路网
    road_path = os.path.join(DIRS['road_network'], "roads_study_area.shp")
    if os.path.exists(road_path):
        roads = gpd.read_file(road_path)
        stats['路网路段数'] = len(roads)
        stats['路网总长度(km)'] = roads['length_m'].sum() / 1000 if 'length_m' in roads.columns else 'N/A'

    # POI
    for name, fname in [('医院', 'hospitals'), ('消防站', 'fire_stations'),
                         ('避难所', 'shelters'), ('地铁站', 'subway_stations'),
                         ('脆弱设施', 'vulnerable_facilities')]:
        path = os.path.join(DIRS['poi'], f"{fname}.shp")
        if os.path.exists(path):
            gdf = gpd.read_file(path)
            stats[f'{name}数量'] = len(gdf)

    # OD
    for name, fname in [('OD天数据', 'od_day_study_area.csv'),
                         ('OD小时数据', 'od_hour_study_area.csv'),
                         ('通勤数据', 'commute_study_area.csv')]:
        path = os.path.join(DIRS['od_data'] if 'OD' in name else DIRS['commute'], fname)
        if os.path.exists(path):
            df = pd.read_csv(path, nrows=0)
            # 快速计数
            with open(path) as f:
                line_count = sum(1 for _ in f) - 1
            stats[f'{name}记录数'] = line_count

    print("\n  数据统计:")
    for k, v in stats.items():
        if isinstance(v, float):
            print(f"    {k}: {v:,.1f}")
        else:
            print(f"    {k}: {v:,}" if isinstance(v, int) else f"    {k}: {v}")

    # ==================================================================
    # 3. 创建事故场景参数文件
    # ==================================================================
    print("\n[3/5] 创建事故场景参数文件...")
    scenario_params = {
        "incident": {
            "location": {"lon": INCIDENT_LON, "lat": INCIDENT_LAT},
            "name": "六环太平桥特种车辆事故",
            "type": "危险气体运输车交通事故",
            "gas_type": "氯气",  # 可修改
            "leak_rate_kg_per_min": 5,
            "leak_duration_min": 60,
            "wind_speed_m_s": 3.0,
            "wind_direction_deg": 225,  # 西南风
            "temperature_c": 15,
            "humidity_pct": 60,
        },
        "closure_zones": {
            "core_closure_radius_m": 500,
            "extended_closure_radius_m": 1000,
            "congestion_radius_m": 3000,
        },
        "evacuation_zones": {
            "danger_radius_m": 1000,
            "warning_radius_m": 3000,
            "safe_radius_m": 5000,
        },
        "time_windows": {
            "rescue_hard_window_min": 30,
            "medical_hard_window_min": 60,
            "protection_soft_window_min": 120,
            "basic_supply_soft_window_min": 240,
        },
        "resources": {
            "emergency_warehouses": [
                {"name": "假设仓库1-丰台", "lon": 116.30, "lat": 39.85, "type": "综合"},
                {"name": "假设仓库2-大兴", "lon": 116.35, "lat": 39.75, "type": "医疗"},
            ],
            "drones": {"count": 10, "max_payload_kg": 25, "max_range_km": 15},
            "trucks": {"count": 20, "avg_speed_kmh": 40},
        }
    }

    param_path = os.path.join(out_dir, "scenario_params.json")
    with open(param_path, 'w', encoding='utf-8') as f:
        json.dump(scenario_params, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 场景参数已保存: {param_path}")
    print("  💡 请根据实际研究需要修改参数值")

    # ==================================================================
    # 4. 复制关键文件到 integrated 目录
    # ==================================================================
    print("\n[4/5] 复制关键文件到整合目录...")
    copy_pairs = [
        (os.path.join(DIRS['study_area'], "study_area_buffer.shp"), "study_area_boundary.shp"),
        (os.path.join(DIRS['road_network'], "roads_study_area.shp"), "road_network.shp"),
        (os.path.join(DIRS['poi'], "hospitals.shp"), "hospitals.shp"),
        (os.path.join(DIRS['poi'], "fire_stations.shp"), "fire_stations.shp"),
        (os.path.join(DIRS['poi'], "shelters.shp"), "shelters.shp"),
    ]
    for src_base, dst_name in copy_pairs:
        # shp 有多个附属文件
        src_dir = os.path.dirname(src_base)
        src_stem = os.path.splitext(os.path.basename(src_base))[0]
        dst_stem = os.path.splitext(dst_name)[0]
        for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg']:
            src = os.path.join(src_dir, src_stem + ext)
            dst = os.path.join(out_dir, dst_stem + ext)
            if os.path.exists(src):
                shutil.copy2(src, dst)

    print(f"  ✅ 已复制至 {out_dir}")

    # ==================================================================
    # 5. 综合可视化
    # ==================================================================
    print("\n[5/5] 生成综合可视化...")
    plot_integration(stats, report, fig_dir)

    # 最终摘要
    print("\n" + "=" * 60)
    print("Step 8 完成 — 数据准备工作全部完成！")
    print("=" * 60)
    print(f"\n  数据完成度: {completed}/{total} ({completed/total*100:.0f}%)")
    print(f"  整合目录: {out_dir}")
    print(f"  场景参数: {param_path}")
    print(f"\n  下一步：")
    print(f"    1. 检查 scenario_params.json，根据研究设计调整参数")
    print(f"    2. 打开 hospitals_list.csv，手动确认医院等级")
    print(f"    3. 开始构建物资配送优化模型 (研究内容一)")
    print(f"    4. 开始构建人员救援疏散模型 (研究内容二)")


def plot_integration(stats, report, fig_dir):
    """综合可视化"""
    fig = plt.figure(figsize=(28, 20))
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.25)

    # 加载所有可用数据
    study_area = gpd.read_file(os.path.join(DIRS['study_area'], "study_area_buffer.shp"))
    core = gpd.read_file(os.path.join(DIRS['study_area'], "yizhuang_boundary.shp"))
    incident = gpd.read_file(os.path.join(DIRS['study_area'], "incident_point.shp"))

    def try_load(path):
        return gpd.read_file(path) if os.path.exists(path) else None

    roads = try_load(os.path.join(DIRS['road_network'], "roads_study_area.shp"))
    hospitals = try_load(os.path.join(DIRS['poi'], "hospitals.shp"))
    fire_stations = try_load(os.path.join(DIRS['poi'], "fire_stations.shp"))
    shelters = try_load(os.path.join(DIRS['poi'], "shelters.shp"))
    subway_st = try_load(os.path.join(DIRS['poi'], "subway_stations.shp"))
    vulnerable = try_load(os.path.join(DIRS['poi'], "vulnerable_facilities.shp"))
    block_pop = try_load(os.path.join(DIRS['population'], "block_pop_study_area.shp"))
    subway_lines = try_load(os.path.join(DIRS['subway'], "subway_lines_network.shp"))

    # ===== 图1: 全要素叠加 (大图) =====
    ax1 = fig.add_subplot(gs[0, 0:2])
    study_area.boundary.plot(ax=ax1, color='#2196F3', linewidth=2, linestyle='--', alpha=0.6)
    core.plot(ax=ax1, color='#FFF8E1', alpha=0.3, edgecolor='#E65100', linewidth=2)
    if roads is not None:
        roads.plot(ax=ax1, color='#E0E0E0', linewidth=0.2)
    if subway_lines is not None:
        subway_lines.plot(ax=ax1, color='#1565C0', linewidth=2.5, alpha=0.7)
    if shelters is not None:
        shelters.plot(ax=ax1, color='#4CAF50', marker='s', markersize=10, alpha=0.4, zorder=6)
    if hospitals is not None:
        hospitals.plot(ax=ax1, color='#D32F2F', marker='P', markersize=40, zorder=8,
                      edgecolor='white', linewidth=0.5)
    if fire_stations is not None:
        fire_stations.plot(ax=ax1, color='#FF6F00', marker='^', markersize=60, zorder=9,
                          edgecolor='white', linewidth=0.5)
    if subway_st is not None:
        subway_st.plot(ax=ax1, color='#1565C0', marker='o', markersize=25, zorder=7,
                      edgecolor='white', linewidth=0.5)
    incident.plot(ax=ax1, color='red', marker='*', markersize=300, zorder=10)

    # 危险区域圈
    inc_proj = incident.to_crs(UTM_CRS)
    for r_m, color, label in [(1000, 'red', '1km 核心危险区'),
                                (3000, 'orange', '3km 警戒区'),
                                (5000, 'yellow', '5km 影响区')]:
        circle = inc_proj.geometry.buffer(r_m)
        circle_wgs = gpd.GeoDataFrame(geometry=circle, crs=UTM_CRS).to_crs(WGS84_CRS)
        circle_wgs.boundary.plot(ax=ax1, color=color, linewidth=1.5, linestyle=':', alpha=0.8)

    legend_items = [
        Line2D([0],[0], marker='*', color='red', linestyle='None', markersize=15, label='事故点'),
        Line2D([0],[0], marker='P', color='#D32F2F', linestyle='None', markersize=10, label='医院'),
        Line2D([0],[0], marker='^', color='#FF6F00', linestyle='None', markersize=10, label='消防站'),
        Line2D([0],[0], marker='s', color='#4CAF50', linestyle='None', markersize=8, label='避难场所'),
        Line2D([0],[0], marker='o', color='#1565C0', linestyle='None', markersize=8, label='地铁站'),
        Line2D([0],[0], color='red', linewidth=1, linestyle=':', label='1km 核心区'),
        Line2D([0],[0], color='orange', linewidth=1, linestyle=':', label='3km 警戒区'),
        Line2D([0],[0], color='yellow', linewidth=1, linestyle=':', label='5km 影响区'),
    ]
    ax1.legend(handles=legend_items, loc='upper left', fontsize=9, framealpha=0.9)
    ax1.set_title('数据全要素叠加检验', fontsize=15, fontweight='bold')
    ax1.set_xlabel('经度 (°E)')
    ax1.set_ylabel('纬度 (°N)')
    ax1.grid(True, alpha=0.2)

    # ===== 图2: 数据完成度 =====
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.axis('off')
    report_text = "数据准备完成度报告\n" + "=" * 35 + "\n"
    for line in report:
        report_text += line + "\n"
    ax2.text(0.05, 0.95, report_text, transform=ax2.transAxes,
             fontsize=9, verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

    # ===== 图3: 核心区域放大 =====
    ax3 = fig.add_subplot(gs[1, 0])
    core.plot(ax=ax3, color='#FFF8E1', alpha=0.3, edgecolor='#E65100', linewidth=2)
    if roads is not None:
        roads.plot(ax=ax3, color='#BDBDBD', linewidth=0.3)
    if hospitals is not None:
        hospitals.plot(ax=ax3, color='#D32F2F', marker='P', markersize=50, zorder=8,
                      edgecolor='white', linewidth=0.5)
    if fire_stations is not None:
        fire_stations.plot(ax=ax3, color='#FF6F00', marker='^', markersize=70, zorder=9,
                          edgecolor='white', linewidth=0.5)
    incident.plot(ax=ax3, color='red', marker='*', markersize=400, zorder=10)

    # zoom to incident ±5km
    pad = 0.05
    ax3.set_xlim(INCIDENT_LON - pad, INCIDENT_LON + pad)
    ax3.set_ylim(INCIDENT_LAT - pad, INCIDENT_LAT + pad)
    ax3.set_title('事故点周边 5km 放大', fontsize=13, fontweight='bold')
    ax3.grid(True, alpha=0.2)

    # ===== 图4: 数据量统计 =====
    ax4 = fig.add_subplot(gs[1, 1])
    if stats:
        keys = list(stats.keys())
        vals = [float(v) if isinstance(v, (int, float)) else 0 for v in stats.values()]
        colors = plt.cm.Set3(np.linspace(0, 1, len(keys)))
        bars = ax4.barh(keys, vals, color=colors, edgecolor='white')
        for bar, val in zip(bars, vals):
            if val > 0:
                ax4.text(bar.get_width() * 1.02, bar.get_y() + bar.get_height()/2,
                        f'{val:,.0f}', va='center', fontsize=8)
    ax4.set_title('各类数据量统计', fontsize=13, fontweight='bold')
    ax4.set_xlabel('数量/长度')

    # ===== 图5: 研究流程示意 =====
    ax5 = fig.add_subplot(gs[1, 2])
    ax5.axis('off')

    flow_text = """
    ┌─────────────────────────────────┐
    │     数据准备完成 ✅              │
    └──────────────┬──────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
    ┌─────────────┐   ┌─────────────┐
    │ 研究内容一   │   │ 研究内容二   │
    │ 物资配送优化 │   │ 人员救援疏散 │
    │             │   │             │
    │ • 货车-无人机│   │ • 时空网络   │
    │   协同      │   │ • 多类型人群 │
    │ • 多物资分类 │   │ • 风险暴露   │
    │ • 时间窗约束 │   │ • 动态分配   │
    └──────┬──────┘   └──────┬──────┘
           │                 │
           └────────┬────────┘
                    ▼
         ┌─────────────────┐
         │  交通仿真验证    │
         │  韧性评估        │
         │  策略建议        │
         └─────────────────┘
    """
    ax5.text(0.05, 0.95, flow_text, transform=ax5.transAxes,
             fontsize=8, verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='#E3F2FD', alpha=0.9))
    ax5.set_title('后续研究路线', fontsize=13, fontweight='bold')

    fig.suptitle('Step 8: 数据整合与检验 — 六环太平桥应急研究', fontsize=20, fontweight='bold', y=1.02)
    fig_path = os.path.join(fig_dir, "step8_integration.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  ✅ 综合大图已保存至 {fig_path}")


if __name__ == '__main__':
    main()
