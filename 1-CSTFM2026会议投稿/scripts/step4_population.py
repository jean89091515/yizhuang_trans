"""
Step 4: 人口数据处理
===================
功能：
  1. 处理地块级人口数据（裁剪到研究范围）
  2. 处理七普年龄结构数据（计算各区脆弱人群比例）
  3. 将年龄结构应用到地块级数据
  4. 估算不同人群类型的空间分布
  5. 可视化

前置条件：先运行 step0_study_area.py
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import warnings
warnings.filterwarnings('ignore')
from config import *

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def load_study_area():
    sa_path = os.path.join(DIRS['study_area'], "study_area_buffer.shp")
    core_path = os.path.join(DIRS['study_area'], "yizhuang_boundary.shp")
    incident_path = os.path.join(DIRS['study_area'], "incident_point.shp")
    return gpd.read_file(sa_path), gpd.read_file(core_path), gpd.read_file(incident_path)


def compute_age_ratios(census_row):
    """从七普数据行计算年龄比例"""
    total = float(census_row.get('total', 0))
    if total == 0:
        return {'children_ratio': 0, 'elderly_ratio': 0, 'working_age_ratio': 0}

    # 0-14岁：儿童
    child_cols = []
    for prefix in ['0_', '1_4_', '5_9_', '10_14_']:
        for suffix in ['男', '女']:
            col = prefix + suffix
            if col in census_row.index:
                child_cols.append(col)
    children = sum(float(census_row.get(c, 0)) for c in child_cols)

    # 60岁及以上：老人
    elderly_cols = []
    for prefix in ['60_64_', '65_69_', '70_74_', '75_79_', '80_84_']:
        for suffix in ['男', '女']:
            col = prefix + suffix
            if col in census_row.index:
                elderly_cols.append(col)
    # 85及以上
    for suffix in ['男', '女']:
        col = f'85及以上{suffix}'
        if col in census_row.index:
            elderly_cols.append(col)
    elderly = sum(float(census_row.get(c, 0)) for c in elderly_cols)

    working = total - children - elderly

    return {
        'children_ratio': children / total,
        'elderly_ratio': elderly / total,
        'working_age_ratio': working / total,
        'children_count': children,
        'elderly_count': elderly,
        'working_age_count': working,
        'total': total,
    }


def main():
    print("=" * 60)
    print("Step 4: 人口数据处理")
    print("=" * 60)

    study_area, core, incident = load_study_area()
    study_polygon = study_area.geometry.values[0]
    out_dir = DIRS['population']
    fig_dir = DIRS['figures']

    # ------------------------------------------------------------------
    # 1. 地块级人口数据
    # ------------------------------------------------------------------
    print("\n[1/4] 处理地块级人口数据...")
    block_pop = gpd.read_file(BLOCK_POP_SHP)
    print(f"  原始坐标系: {block_pop.crs}")
    print(f"  总地块数: {len(block_pop)}")
    print(f"  字段: {list(block_pop.columns)}")

    # 确保坐标系为 WGS84
    if block_pop.crs and block_pop.crs != WGS84_CRS:
        block_pop = block_pop.to_crs(WGS84_CRS)
    elif block_pop.crs is None:
        print("  ⚠️ 无坐标系信息，假设为 WGS84")
        block_pop = block_pop.set_crs(WGS84_CRS)

    # 裁剪到研究范围
    block_study = gpd.clip(block_pop, study_polygon)
    print(f"  研究范围内地块数: {len(block_study)}")

    # 打印数值型字段统计（帮助判断哪个字段是人口数）
    print("\n  数值字段统计:")
    for col in block_study.select_dtypes(include=[np.number]).columns:
        if col != 'geometry':
            vals = block_study[col].dropna()
            if len(vals) > 0:
                print(f"    {col}: min={vals.min():.1f}, max={vals.max():.1f}, "
                      f"mean={vals.mean():.1f}, sum={vals.sum():.0f}")

    # ------------------------------------------------------------------
    # 2. 七普年龄结构数据
    # ------------------------------------------------------------------
    print("\n[2/4] 处理七普年龄结构数据...")
    census = gpd.read_file(CENSUS_SHP)
    print(f"  全国区县数: {len(census)}")

    # 筛选北京市
    # 尝试不同的筛选方式
    bj_census = census[
        (census['地级'].str.contains('北京', na=False)) |
        (census['省级'].str.contains('北京', na=False)) |
        (census['地级码'].astype(str).str.startswith('1101'))
    ]
    print(f"  北京区县数: {len(bj_census)}")

    # 计算各区年龄结构
    age_results = []
    for _, row in bj_census.iterrows():
        ratios = compute_age_ratios(row)
        ratios['district_name'] = row.get('地名', row.get('县级', ''))
        ratios['district_code'] = row.get('区划码', row.get('县级码', ''))
        age_results.append(ratios)

    age_df = pd.DataFrame(age_results)
    print("\n  北京各区年龄结构:")
    print(f"  {'区县名':12s} {'总人口':>10s} {'儿童(0-14)':>10s} {'老人(60+)':>10s} {'劳动力':>10s}")
    print("  " + "-" * 55)
    for _, row in age_df.iterrows():
        print(f"  {row['district_name']:12s} {row['total']:10,.0f} "
              f"{row['children_ratio']:10.1%} {row['elderly_ratio']:10.1%} "
              f"{row['working_age_ratio']:10.1%}")

    # 保存年龄结构
    age_df.to_csv(os.path.join(out_dir, "age_structure_by_district.csv"),
                  index=False, encoding='utf-8-sig')

    # ------------------------------------------------------------------
    # 3. 将年龄结构应用到地块数据（空间匹配）
    # ------------------------------------------------------------------
    print("\n[3/4] 空间匹配 — 将年龄结构应用到地块...")

    # 将七普区县数据转为 WGS84
    if bj_census.crs and bj_census.crs != WGS84_CRS:
        bj_census = bj_census.to_crs(WGS84_CRS)

    # 空间连接：判断每个地块属于哪个区县
    block_with_district = gpd.sjoin(
        block_study, bj_census[['geometry', '地名', '区划码']],
        how='left', predicate='intersects'
    )

    # 从 age_df 获取比例，合并到地块数据
    age_ratio_cols = age_df[['district_code', 'children_ratio', 'elderly_ratio', 'working_age_ratio']]
    block_with_district = block_with_district.merge(
        age_ratio_cols, left_on='区划码', right_on='district_code', how='left'
    )

    # 如果匹配失败，使用全区平均
    avg_child = age_df['children_ratio'].mean()
    avg_elderly = age_df['elderly_ratio'].mean()
    avg_working = age_df['working_age_ratio'].mean()
    block_with_district['children_ratio'] = block_with_district['children_ratio'].fillna(avg_child)
    block_with_district['elderly_ratio'] = block_with_district['elderly_ratio'].fillna(avg_elderly)
    block_with_district['working_age_ratio'] = block_with_district['working_age_ratio'].fillna(avg_working)

    # 找出人口字段（需要根据实际数据调整）
    # 尝试常见字段名
    pop_col = None
    for candidate in ['pop', 'population', 'POP', 'POPULATION', 'pop_count',
                      'total', 'Total', 'TOTAL', 'count', 'COUNT', 'num', 'value']:
        if candidate in block_with_district.columns:
            pop_col = candidate
            break

    if pop_col is None:
        # 使用第一个数值列
        num_cols = block_with_district.select_dtypes(include=[np.number]).columns.tolist()
        num_cols = [c for c in num_cols if c not in ['index_right', 'children_ratio',
                     'elderly_ratio', 'working_age_ratio']]
        if num_cols:
            pop_col = num_cols[0]
            print(f"  ⚠️ 未找到明确人口字段，使用 '{pop_col}' 作为人口字段")

    if pop_col:
        block_with_district['pop_children'] = block_with_district[pop_col] * block_with_district['children_ratio']
        block_with_district['pop_elderly'] = block_with_district[pop_col] * block_with_district['elderly_ratio']
        block_with_district['pop_working'] = block_with_district[pop_col] * block_with_district['working_age_ratio']
        print(f"\n  人口字段: {pop_col}")
        print(f"  研究范围内总人口: {block_with_district[pop_col].sum():,.0f}")
        print(f"    儿童 (0-14): {block_with_district['pop_children'].sum():,.0f}")
        print(f"    老人 (60+):  {block_with_district['pop_elderly'].sum():,.0f}")
        print(f"    劳动力:      {block_with_district['pop_working'].sum():,.0f}")
    else:
        print("  ⚠️ 未找到人口数值字段，请手动指定 pop_col 变量")

    # ------------------------------------------------------------------
    # 4. 保存
    # ------------------------------------------------------------------
    print("\n[4/4] 保存文件...")
    # 清理可能导致保存问题的列
    save_cols = [c for c in block_with_district.columns
                 if c not in ['index_right', 'district_code']]
    block_save = block_with_district[save_cols].copy()
    block_save.to_file(os.path.join(out_dir, "block_pop_study_area.shp"), encoding='utf-8')
    print(f"  ✅ 已保存至 {out_dir}")

    # ------------------------------------------------------------------
    # 可视化
    # ------------------------------------------------------------------
    print("\n正在生成可视化...")
    plot_population(block_with_district, bj_census, age_df,
                    study_area, core, incident, pop_col, fig_dir)


def plot_population(block_pop, bj_census, age_df, study_area, core, incident, pop_col, fig_dir):
    """人口数据可视化"""

    fig = plt.figure(figsize=(24, 16))
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3)

    # ===== 图1: 人口密度分布 =====
    ax1 = fig.add_subplot(gs[0, 0:2])
    study_area.boundary.plot(ax=ax1, color='#2196F3', linewidth=1.5, linestyle='--', alpha=0.5)
    core.boundary.plot(ax=ax1, color='#E65100', linewidth=2)

    if pop_col and pop_col in block_pop.columns:
        pop_nonzero = block_pop[block_pop[pop_col] > 0]
        if len(pop_nonzero) > 0:
            pop_nonzero.plot(ax=ax1, column=pop_col, cmap='YlOrRd',
                            legend=True, legend_kwds={'label': '人口数', 'shrink': 0.6},
                            markersize=2, alpha=0.7)

    incident.plot(ax=ax1, color='blue', marker='*', markersize=200, zorder=10)
    ax1.set_title('研究范围人口空间分布', fontsize=14, fontweight='bold')
    ax1.set_xlabel('经度 (°E)')
    ax1.set_ylabel('纬度 (°N)')
    ax1.grid(True, alpha=0.2)

    # ===== 图2: 北京各区年龄结构 =====
    ax2 = fig.add_subplot(gs[0, 2])
    age_sorted = age_df.sort_values('total', ascending=True).tail(10)
    y_pos = range(len(age_sorted))
    ax2.barh(y_pos, age_sorted['children_ratio'] * 100, color='#42A5F5', label='儿童(0-14)')
    ax2.barh(y_pos, age_sorted['elderly_ratio'] * 100,
             left=age_sorted['children_ratio'] * 100, color='#EF5350', label='老人(60+)')
    ax2.barh(y_pos, age_sorted['working_age_ratio'] * 100,
             left=(age_sorted['children_ratio'] + age_sorted['elderly_ratio']) * 100,
             color='#66BB6A', label='劳动力(15-59)')
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(age_sorted['district_name'])
    ax2.set_xlabel('占比 (%)')
    ax2.set_title('北京各区人口年龄结构', fontsize=13, fontweight='bold')
    ax2.legend(loc='lower right', fontsize=8)

    # ===== 图3: 儿童人口分布 =====
    ax3 = fig.add_subplot(gs[1, 0])
    study_area.boundary.plot(ax=ax3, color='#2196F3', linewidth=1, linestyle='--', alpha=0.4)
    core.boundary.plot(ax=ax3, color='#E65100', linewidth=1.5)
    if 'pop_children' in block_pop.columns:
        nonzero = block_pop[block_pop['pop_children'] > 0]
        if len(nonzero) > 0:
            nonzero.plot(ax=ax3, column='pop_children', cmap='Blues',
                        legend=True, legend_kwds={'label': '儿童人口', 'shrink': 0.5},
                        markersize=2, alpha=0.7)
    ax3.set_title('儿童人口(0-14岁)分布', fontsize=13, fontweight='bold')
    ax3.grid(True, alpha=0.2)

    # ===== 图4: 老人人口分布 =====
    ax4 = fig.add_subplot(gs[1, 1])
    study_area.boundary.plot(ax=ax4, color='#2196F3', linewidth=1, linestyle='--', alpha=0.4)
    core.boundary.plot(ax=ax4, color='#E65100', linewidth=1.5)
    if 'pop_elderly' in block_pop.columns:
        nonzero = block_pop[block_pop['pop_elderly'] > 0]
        if len(nonzero) > 0:
            nonzero.plot(ax=ax4, column='pop_elderly', cmap='Reds',
                        legend=True, legend_kwds={'label': '老年人口', 'shrink': 0.5},
                        markersize=2, alpha=0.7)
    ax4.set_title('老年人口(60岁+)分布', fontsize=13, fontweight='bold')
    ax4.grid(True, alpha=0.2)

    # ===== 图5: 人群分类模型示意 =====
    ax5 = fig.add_subplot(gs[1, 2])
    ax5.axis('off')

    # 绘制人群分类表
    table_data = [
        ['第一类(k=1)', '重伤/中毒者', 'ω₁=10', '必须送往医院'],
        ['第二类(k=2)', '老人/儿童/孕妇', 'ω₂=5', '优先医院/庇护所'],
        ['第三类(k=3)', '一般健康人员', 'ω₃=1', '疏散至任意庇护所'],
    ]
    col_labels = ['类别', '人群特征', '权重', '目的地要求']

    table = ax5.table(cellText=table_data, colLabels=col_labels,
                      cellLoc='center', loc='center',
                      colWidths=[0.18, 0.28, 0.14, 0.35])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)

    # 表头颜色
    for j in range(4):
        table[(0, j)].set_facecolor('#1976D2')
        table[(0, j)].set_text_props(color='white', fontweight='bold')
    # 行颜色
    row_colors = ['#FFCDD2', '#FFF9C4', '#C8E6C9']
    for i in range(3):
        for j in range(4):
            table[(i+1, j)].set_facecolor(row_colors[i])

    ax5.set_title('人群分类模型\n(用于疏散优先级)', fontsize=13, fontweight='bold', pad=20)

    if pop_col and pop_col in block_pop.columns:
        total = block_pop[pop_col].sum()
        info = (f"研究范围总人口: {total:,.0f}\n"
                f"儿童(0-14): {block_pop.get('pop_children', pd.Series([0])).sum():,.0f}\n"
                f"老人(60+): {block_pop.get('pop_elderly', pd.Series([0])).sum():,.0f}")
        ax5.text(0.5, 0.05, info, transform=ax5.transAxes, fontsize=10,
                ha='center', style='italic',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    fig.suptitle('Step 4: 人口数据处理结果', fontsize=18, fontweight='bold', y=1.01)
    fig_path = os.path.join(fig_dir, "step4_population.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  ✅ 图片已保存至 {fig_path}")


if __name__ == '__main__':
    main()
