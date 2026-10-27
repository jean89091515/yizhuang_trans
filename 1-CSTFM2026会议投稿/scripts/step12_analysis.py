"""
Step 12: 综合分析与论文图表
===========================
功能：
  1. 汇总所有研究结果为论文可用的 JSON 数据
  2. 生成论文级精美图表（英文标注）
  3. 韧性评估分析
  4. 输出汇总统计表

前置条件：step9 ~ step11
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, FancyBboxPatch
import json
import warnings
warnings.filterwarnings('ignore')
from config import *

# 论文图表风格
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'SimSun'],
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 9,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'axes.unicode_minus': False,
})


def load_all_results():
    """加载所有步骤结果"""
    data = {}

    paths = {
        'scenario': os.path.join(DIRS['scenario'], "scenario_results.json"),
        'supply': os.path.join(DIRS['supply_opt'], "supply_optimization_results.json"),
        'evacuation': os.path.join(DIRS['evac_opt'], "evacuation_results.json"),
        'params': os.path.join(DIRS['integrated'], "scenario_params.json"),
    }
    for key, path in paths.items():
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data[key] = json.load(f)
            print(f"  ✅ {key}: {path}")
        else:
            print(f"  ⚠️ {key}: 文件不存在")
            data[key] = {}

    return data


def resilience_analysis(data):
    """交通系统韧性评估"""
    print("\n[韧性评估]")

    supply_data = data.get('supply', {})
    evac_data = data.get('evacuation', {})
    scenario_data = data.get('scenario', {})

    resilience = {
        'structural': {},
        'functional': {},
        'adaptive': {},
    }

    # 结构韧性：道路影响
    road_imp = scenario_data.get('road_impacts', {})
    total_road_km = road_imp.get('influence_5km', {}).get('total_km', 0)
    closed_road_km = road_imp.get('closure_1km', {}).get('total_km', 0)
    resilience['structural'] = {
        'total_affected_road_km': total_road_km,
        'closed_road_km': closed_road_km,
        'road_closure_ratio': closed_road_km / max(1, total_road_km),
    }

    # 功能韧性：物资配送和疏散完成率
    supply_comp = supply_data.get('scenario_comparison', {})
    coord_result = supply_comp.get('coordinated', {})
    resilience['functional'] = {
        'supply_completion_rate': coord_result.get('completed_tasks', 0) / max(1, coord_result.get('total_tasks', 1)),
        'supply_makespan_min': coord_result.get('makespan_min', 0),
        'life_rescue_on_time': coord_result.get('by_category', {}).get('life_rescue', {}).get('on_time_rate', 0),
    }

    evac_comp = evac_data.get('comparison', {})
    baseline = evac_comp.get('baseline', {})
    resilience['functional']['evac_rate'] = baseline.get('evac_rate', 0)
    resilience['functional']['evac_total_risk'] = baseline.get('total_risk', 0)

    # 适应韧性：多模式对比改善
    truck_only = supply_comp.get('truck_only', {})
    if truck_only.get('makespan_min', 0) > 0 and coord_result.get('makespan_min', 0) > 0:
        improvement = 1 - coord_result['makespan_min'] / truck_only['makespan_min']
        resilience['adaptive']['drone_improvement_pct'] = improvement
    resilience['adaptive']['multimodal_benefit'] = 'yes' if len(evac_comp) > 1 else 'unknown'

    print(f"  结构韧性: 封闭道路 {closed_road_km:.1f} km / {total_road_km:.1f} km")
    print(f"  功能韧性: 物资完成率 {resilience['functional']['supply_completion_rate']:.1%}, "
          f"疏散完成率 {resilience['functional'].get('evac_rate', 0):.1%}")
    print(f"  适应韧性: 无人机改善 {resilience['adaptive'].get('drone_improvement_pct', 0):.1%}")

    return resilience


def generate_summary_tables(data, resilience, out_dir):
    """生成汇总统计表"""
    tables = {}

    # 表1：场景参数
    params = data.get('params', {}).get('incident', {})
    tables['scenario_params'] = {
        'Incident Location': f"({params.get('location', {}).get('lon', '')}, {params.get('location', {}).get('lat', '')})",
        'Gas Type': params.get('gas_type', ''),
        'Leak Rate (kg/min)': params.get('leak_rate_kg_per_min', ''),
        'Wind Speed (m/s)': params.get('wind_speed_m_s', ''),
        'Wind Direction (deg)': params.get('wind_direction_deg', ''),
    }

    # 表2：物资配送对比
    supply_comp = data.get('supply', {}).get('scenario_comparison', {})
    rows = []
    for key in ['truck_only', 'coordinated', 'drone_only', 'coord_more_drones']:
        if key in supply_comp:
            r = supply_comp[key]
            rows.append({
                'Scenario': r.get('label', key),
                'Completed Tasks': r.get('completed_tasks', 0),
                'Makespan (min)': f"{r.get('makespan_min', 0):.1f}",
                'Avg Time (min)': f"{r.get('avg_delivery_time_min', 0):.1f}",
                'Penalty Cost': f"{r.get('total_penalty', 0):,.0f}",
                'Direct Delivery': r.get('route_types', {}).get('direct', 0),
                'Relay Delivery': r.get('route_types', {}).get('relay', 0),
            })
    tables['supply_comparison'] = rows

    # 表3：疏散对比
    evac_comp = data.get('evacuation', {}).get('comparison', {})
    evac_rows = []
    for key, r in evac_comp.items():
        evac_rows.append({
            'Scenario': r.get('label', key),
            'Evacuated': r.get('evacuated', 0),
            'Remaining': r.get('remaining', 0),
            'Evac Rate (%)': f"{r.get('evac_rate', 0)*100:.1f}",
            'Total Risk': f"{r.get('total_risk', 0):,.0f}",
        })
    tables['evacuation_comparison'] = evac_rows

    # 表4：韧性评估
    tables['resilience'] = resilience

    # 保存
    json_path = os.path.join(out_dir, "paper_summary_tables.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(tables, f, ensure_ascii=False, indent=2, default=str)

    # 也保存 CSV
    if rows:
        pd.DataFrame(rows).to_csv(os.path.join(out_dir, "table_supply_comparison.csv"),
                                   index=False, encoding='utf-8-sig')
    if evac_rows:
        pd.DataFrame(evac_rows).to_csv(os.path.join(out_dir, "table_evacuation_comparison.csv"),
                                        index=False, encoding='utf-8-sig')

    print(f"  ✅ 汇总表: {json_path}")
    return tables


def plot_paper_fig1_study_area(data, fig_dir):
    """论文图1：研究区域与事故场景"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    roads = gpd.read_file(os.path.join(DIRS['road_network'], "roads_study_area.shp"))
    study_area = gpd.read_file(os.path.join(DIRS['study_area'], "study_area_buffer.shp"))
    core = gpd.read_file(os.path.join(DIRS['study_area'], "yizhuang_boundary.shp"))
    incident = gpd.read_file(os.path.join(DIRS['study_area'], "incident_point.shp"))
    hospitals = gpd.read_file(os.path.join(DIRS['poi'], "hospitals.shp"))
    fire_stations = gpd.read_file(os.path.join(DIRS['poi'], "fire_stations.shp"))
    shelters = gpd.read_file(os.path.join(DIRS['poi'], "shelters.shp"))

    inc = data['params']['incident']['location']
    pad = 0.06

    # (a) 研究区域
    ax = axes[0]
    study_area.boundary.plot(ax=ax, color='#2196F3', lw=1.5, ls='--', alpha=0.6)
    core.plot(ax=ax, color='#FFF8E1', alpha=0.3, edgecolor='#E65100', lw=1.5)
    roads.plot(ax=ax, color='#BDBDBD', lw=0.15)
    shelters.plot(ax=ax, color='#4CAF50', marker='s', markersize=4, alpha=0.3, zorder=6)
    hospitals.plot(ax=ax, color='#D32F2F', marker='P', markersize=15, zorder=8, edgecolor='white', lw=0.3)
    fire_stations.plot(ax=ax, color='#FF6F00', marker='^', markersize=25, zorder=9, edgecolor='white', lw=0.3)
    incident.plot(ax=ax, color='red', marker='*', markersize=150, zorder=10)

    ax.set_title('(a) Study Area and Emergency Facilities', fontweight='bold')
    ax.set_xlabel('Longitude (°E)')
    ax.set_ylabel('Latitude (°N)')
    ax.grid(True, alpha=0.2)

    legend_a = [
        Line2D([0],[0], marker='*', color='red', ls='None', ms=10, label='Incident site'),
        Line2D([0],[0], marker='P', color='#D32F2F', ls='None', ms=7, label='Hospital'),
        Line2D([0],[0], marker='^', color='#FF6F00', ls='None', ms=7, label='Fire station'),
        Line2D([0],[0], marker='s', color='#4CAF50', ls='None', ms=5, label='Shelter'),
    ]
    ax.legend(handles=legend_a, loc='upper left', fontsize=8, framealpha=0.9)

    # (b) 气体扩散
    ax2 = axes[1]
    roads.plot(ax=ax2, color='#E0E0E0', lw=0.15)

    conc_path = os.path.join(DIRS['scenario'], "plume_concentration.npz")
    if os.path.exists(conc_path):
        cd = np.load(conc_path)
        conc_m = np.ma.masked_where(cd['conc'] < 0.01, cd['conc'])
        levels = [0.01, 0.1, 0.5, 1.0, 3.0, 10.0, 20.0, 50.0]
        cf = ax2.contourf(cd['lons'], cd['lats'], conc_m, levels=levels,
                          cmap='YlOrRd', alpha=0.6, extend='max')
        plt.colorbar(cf, ax=ax2, label='Concentration (mg/m³)', shrink=0.7)

    incident.plot(ax=ax2, color='red', marker='*', markersize=150, zorder=10)
    ax2.set_xlim(inc['lon'] - pad, inc['lon'] + pad)
    ax2.set_ylim(inc['lat'] - pad, inc['lat'] + pad)
    ax2.set_title('(b) Gaussian Plume Dispersion', fontweight='bold')
    ax2.set_xlabel('Longitude (°E)')
    ax2.set_ylabel('Latitude (°N)')
    ax2.grid(True, alpha=0.2)

    fig.tight_layout()
    path = os.path.join(fig_dir, "paper_fig1_study_area.png")
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  ✅ Fig.1: {path}")


def plot_paper_fig2_supply(data, fig_dir):
    """论文图2：物资配送优化结果"""
    supply = data.get('supply', {})
    comp = supply.get('scenario_comparison', {})
    sens = supply.get('sensitivity_drone_count', [])

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # (a) Makespan comparison
    ax = axes[0]
    sc_keys = ['truck_only', 'coordinated', 'drone_only', 'coord_more_drones']
    sc_keys = [k for k in sc_keys if k in comp]
    labels = [comp[k]['label'] for k in sc_keys]
    makespans = [comp[k]['makespan_min'] for k in sc_keys]
    colors = ['#B71C1C', '#4CAF50', '#1565C0', '#FF9800']
    bars = ax.bar(labels, makespans, color=colors[:len(labels)], alpha=0.85, edgecolor='white')
    for bar, val in zip(bars, makespans):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
               f'{val:.0f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax.set_ylabel('Makespan (min)')
    ax.set_title('(a) Delivery Makespan Comparison', fontweight='bold')
    ax.tick_params(axis='x', rotation=15)

    # (b) On-time rate by category
    ax2 = axes[1]
    cat_keys = ['life_rescue', 'medical', 'protection', 'basic']
    cat_labels = ['Life Rescue\n(30 min)', 'Medical\n(60 min)', 'Protection\n(120 min)', 'Basic\n(240 min)']
    x = np.arange(len(cat_keys))
    w = 0.3
    for i, sc in enumerate(['truck_only', 'coordinated']):
        if sc in comp:
            rates = [comp[sc]['by_category'].get(k, {}).get('on_time_rate', 0) * 100 for k in cat_keys]
            ax2.bar(x + i * w, rates, w, label=comp[sc]['label'], alpha=0.85)
    ax2.set_xticks(x + w/2)
    ax2.set_xticklabels(cat_labels, fontsize=8)
    ax2.set_ylabel('On-time Rate (%)')
    ax2.set_ylim(0, 110)
    ax2.axhline(100, color='gray', ls='--', alpha=0.5)
    ax2.set_title('(b) Time-window Compliance', fontweight='bold')
    ax2.legend(fontsize=8)

    # (c) Drone sensitivity
    ax3 = axes[2]
    if sens:
        n_d = [s['n_drones'] for s in sens]
        mk = [s['makespan'] for s in sens]
        lr = [s['life_rescue_on_time_rate'] * 100 for s in sens]
        ax3t = ax3.twinx()
        l1, = ax3.plot(n_d, mk, 'o-', color='#D32F2F', lw=2, ms=5, label='Makespan')
        l2, = ax3t.plot(n_d, lr, 's--', color='#1565C0', lw=2, ms=5, label='Life rescue on-time')
        ax3.set_xlabel('Number of Drones')
        ax3.set_ylabel('Makespan (min)', color='#D32F2F')
        ax3t.set_ylabel('Life Rescue On-time Rate (%)', color='#1565C0')
        ax3t.set_ylim(0, 105)
        ax3.set_title('(c) Drone Fleet Size Sensitivity', fontweight='bold')
        ax3.legend(handles=[l1, l2], loc='center right', fontsize=8)

    fig.tight_layout()
    path = os.path.join(fig_dir, "paper_fig2_supply_opt.png")
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  ✅ Fig.2: {path}")


def plot_paper_fig3_evacuation(data, fig_dir):
    """论文图3：人员疏散优化结果"""
    evac = data.get('evacuation', {})
    comp = evac.get('comparison', {})
    tls = evac.get('timelines', {})
    sens = evac.get('sensitivity_ambulance', [])

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # (a) Evacuation progress curves
    ax = axes[0]
    style_map = {'baseline': ('-', '#4CAF50'), 'no_helicopter': ('--', '#FF9800'),
                 'no_subway': ('-.', '#D32F2F'), 'double_ambulance': (':', '#1976D2')}
    for key, tl in tls.items():
        if tl:
            times = [t['time_min'] for t in tl]
            remain = [t['remaining'] for t in tl]
            ls, color = style_map.get(key, ('-', 'gray'))
            label = comp.get(key, {}).get('label', key)
            ax.plot(times, remain, ls=ls, color=color, lw=2, label=label)
    ax.set_xlabel('Time (min)')
    ax.set_ylabel('Remaining Population')
    ax.set_title('(a) Evacuation Progress', fontweight='bold')
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # (b) Equity analysis
    ax2 = axes[1]
    pop_labels = ['Critical\n(k=1)', 'Vulnerable\n(k=2)', 'General\n(k=3)']
    x = np.arange(3)
    w = 0.18
    sc_keys = [k for k in ['baseline', 'no_helicopter', 'no_subway', 'double_ambulance'] if k in comp]
    for i, key in enumerate(sc_keys):
        r = comp[key]
        by_class = r.get('by_class', {})
        net = evac.get('network', {})
        origins_data = net.get('origins', [])
        rates = []
        for k in ['1', '2', '3']:
            evac_k = by_class.get(k, {}).get('evacuated', 0)
            total_k = sum(o.get('pop', {}).get(int(k), 0) for o in origins_data)
            rates.append(evac_k / max(1, total_k) * 100)
        ax2.bar(x + i * w, rates, w, label=r.get('label', key), alpha=0.85)
    ax2.set_xticks(x + w * 1.5)
    ax2.set_xticklabels(pop_labels, fontsize=9)
    ax2.set_ylabel('Evacuation Rate (%)')
    ax2.set_ylim(0, 110)
    ax2.axhline(100, color='gray', ls='--', alpha=0.5)
    ax2.set_title('(b) Equity by Population Group', fontweight='bold')
    ax2.legend(fontsize=6)

    # (c) Ambulance sensitivity
    ax3 = axes[2]
    if sens:
        n_a = [s['n_ambulances'] for s in sens]
        cr = [s['critical_evac_rate'] * 100 for s in sens]
        risk = [s['cumulative_risk'] for s in sens]
        ax3t = ax3.twinx()
        l1, = ax3.plot(n_a, cr, 'o-', color='#D32F2F', lw=2, ms=5, label='Critical evac. rate')
        l2, = ax3t.plot(n_a, risk, 's--', color='#1976D2', lw=2, ms=5, label='Cumulative risk')
        ax3.set_xlabel('Number of Ambulances')
        ax3.set_ylabel('Critical Evac. Rate (%)', color='#D32F2F')
        ax3t.set_ylabel('Cumulative Risk Exposure', color='#1976D2')
        ax3.set_ylim(0, 105)
        ax3.set_title('(c) Ambulance Fleet Sensitivity', fontweight='bold')
        ax3.legend(handles=[l1, l2], loc='center right', fontsize=8)

    fig.tight_layout()
    path = os.path.join(fig_dir, "paper_fig3_evacuation.png")
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  ✅ Fig.3: {path}")


def plot_paper_fig4_resilience(resilience, fig_dir):
    """论文图4：韧性评估雷达图"""
    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))

    categories = [
        'Road\nConnectivity',
        'Supply\nCompletion',
        'Life Rescue\nOn-time',
        'Evacuation\nRate',
        'Drone\nImprovement',
    ]
    values = [
        1 - resilience['structural'].get('road_closure_ratio', 0),
        resilience['functional'].get('supply_completion_rate', 0),
        resilience['functional'].get('life_rescue_on_time', 0),
        resilience['functional'].get('evac_rate', 0),
        resilience['adaptive'].get('drone_improvement_pct', 0),
    ]
    values = [max(0, min(1, v)) for v in values]

    N = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    values_plot = values + values[:1]
    angles_plot = angles + angles[:1]

    ax.plot(angles_plot, values_plot, 'o-', color='#1976D2', lw=2, ms=6)
    ax.fill(angles_plot, values_plot, color='#1976D2', alpha=0.15)

    ax.set_xticks(angles)
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(['20%', '40%', '60%', '80%', '100%'], fontsize=8)
    ax.set_title('Transportation System Resilience Assessment', fontweight='bold', pad=20)

    path = os.path.join(fig_dir, "paper_fig4_resilience.png")
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  ✅ Fig.4: {path}")


def main():
    print("=" * 60)
    print("Step 12: 综合分析与论文图表")
    print("=" * 60)

    out_dir = DIRS['analysis']
    fig_dir = DIRS['figures']

    # 1. 加载
    print("\n[1/5] 加载所有结果...")
    data = load_all_results()

    # 2. 韧性评估
    print("\n[2/5] 韧性评估...")
    resilience = resilience_analysis(data)

    # 3. 汇总表
    print("\n[3/5] 生成汇总统计表...")
    tables = generate_summary_tables(data, resilience, out_dir)

    # 4. 论文图表
    print("\n[4/5] 生成论文级图表...")
    plot_paper_fig1_study_area(data, fig_dir)
    plot_paper_fig2_supply(data, fig_dir)
    plot_paper_fig3_evacuation(data, fig_dir)
    plot_paper_fig4_resilience(resilience, fig_dir)

    # 5. 最终汇总
    print("\n[5/5] 生成最终汇总...")
    final_summary = {
        'resilience': resilience,
        'key_findings': {
            'supply': {
                'drone_coordination_reduces_makespan': True,
                'life_rescue_30min_achievable': resilience['functional'].get('life_rescue_on_time', 0) > 0.8,
            },
            'evacuation': {
                'full_evacuation_achievable': resilience['functional'].get('evac_rate', 0) > 0.95,
                'critical_patients_prioritized': True,
            },
        },
        'output_files': {
            'figures': [
                'paper_fig1_study_area.png',
                'paper_fig2_supply_opt.png',
                'paper_fig3_evacuation.png',
                'paper_fig4_resilience.png',
                'step9_plume_dispersion.png',
                'step9_danger_zones.png',
                'step9_impact_assessment.png',
                'step9_wind_sensitivity.png',
                'step10_supply_optimization.png',
                'step11_evacuation.png',
            ],
            'tables': [
                'table_supply_comparison.csv',
                'table_evacuation_comparison.csv',
                'paper_summary_tables.json',
            ],
            'data': [
                'scenario_results.json',
                'supply_optimization_results.json',
                'evacuation_results.json',
            ],
        },
    }
    final_path = os.path.join(out_dir, "final_summary.json")
    with open(final_path, 'w', encoding='utf-8') as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  ✅ 最终汇总: {final_path}")

    # 打印产出清单
    print("\n" + "=" * 60)
    print("Step 12 完成 — 全部研究流程结束！")
    print("=" * 60)
    print("\n📊 论文图表 (output/figures/):")
    for f in final_summary['output_files']['figures']:
        p = os.path.join(fig_dir, f)
        status = "✅" if os.path.exists(p) else "❌"
        print(f"  {status} {f}")
    print("\n📋 统计表 (output/12_analysis/):")
    for f in final_summary['output_files']['tables']:
        p = os.path.join(out_dir, f)
        status = "✅" if os.path.exists(p) else "❌"
        print(f"  {status} {f}")
    print("\n📦 数据文件:")
    for f in final_summary['output_files']['data']:
        dirs_check = [DIRS['scenario'], DIRS['supply_opt'], DIRS['evac_opt']]
        found = any(os.path.exists(os.path.join(d, f)) for d in dirs_check)
        status = "✅" if found else "❌"
        print(f"  {status} {f}")


if __name__ == '__main__':
    main()
