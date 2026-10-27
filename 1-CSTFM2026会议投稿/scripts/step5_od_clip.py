"""
Step 5: OD 与通勤数据裁剪
=========================
功能：
  1. 百度坐标转 WGS84（调用 coord_transform.py）
  2. 裁剪 OD 天/小时数据到研究范围
  3. 裁剪通勤数据到研究范围
  4. 统计出行时空特征
  5. 可视化

前置条件：先运行 step0_study_area.py

⚠️ 注意：全北京 OD 数据量很大，此脚本使用"粗筛+精筛"两步策略节省时间。
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import Point
from shapely.prepared import prep
import glob
import warnings
warnings.filterwarnings('ignore')
from config import *
from coord_transform import bd09_to_wgs84

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def load_study_area():
    sa_path = os.path.join(DIRS['study_area'], "study_area_buffer.shp")
    study_area = gpd.read_file(sa_path)
    return study_area.geometry.values[0]


def get_bbox_filter(study_polygon, margin=0.02):
    """获取粗筛经纬度范围（BD-09 坐标下，加额外余量）"""
    bounds = study_polygon.bounds  # (minx, miny, maxx, maxy) WGS84
    # BD-09 相比 WGS84 整体偏东偏北约 0.006-0.01 度，加余量
    return {
        'lon_min': bounds[0] - margin,
        'lon_max': bounds[2] + margin,
        'lat_min': bounds[1] - margin,
        'lat_max': bounds[3] + margin,
    }


def batch_bd09_to_wgs84(lons, lats):
    """向量化坐标转换（用 numpy 加速）"""
    wgs_lons = np.empty_like(lons)
    wgs_lats = np.empty_like(lats)
    for i in range(len(lons)):
        wgs_lons[i], wgs_lats[i] = bd09_to_wgs84(lons[i], lats[i])
    return wgs_lons, wgs_lats


def process_od_files(file_pattern, file_type, study_polygon, bbox):
    """处理 OD 数据文件（天尺度或小时尺度）"""
    files = sorted(glob.glob(file_pattern))
    if not files:
        print(f"  ⚠️ 未找到匹配文件: {file_pattern}")
        return pd.DataFrame()

    print(f"  找到 {len(files)} 个文件")
    all_dfs = []

    for i, f in enumerate(files):
        fname = os.path.basename(f)
        print(f"  [{i+1}/{len(files)}] 处理 {fname}...")

        # 读取
        df = pd.read_csv(f, sep='\t', dtype=str)
        n_orig = len(df)

        # 确定坐标列
        if file_type == 'cf_day':
            ox, oy = '起点网格中心x坐标', '起点网格中心y坐标'
            dx, dy = '终点网格中心x坐标', '终点网格中心y坐标'
        elif file_type == 'cf_hour':
            ox, oy = '起点网格中心x坐标', '起点网格中心y坐标'
            dx, dy = '终点网格中心x坐标', '终点网格中心y坐标'
        else:
            ox, oy = '居住地网格中心x坐标', '居住地网格中心y坐标'
            dx, dy = '工作地网格中心x坐标', '工作地网格中心y坐标'

        # 转数值
        for col in [ox, oy, dx, dy]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=[ox, oy, dx, dy])

        # 第一步：粗筛（BD-09 坐标下）
        mask = (
            ((df[ox] >= bbox['lon_min']) & (df[ox] <= bbox['lon_max']) &
             (df[oy] >= bbox['lat_min']) & (df[oy] <= bbox['lat_max'])) |
            ((df[dx] >= bbox['lon_min']) & (df[dx] <= bbox['lon_max']) &
             (df[dy] >= bbox['lat_min']) & (df[dy] <= bbox['lat_max']))
        )
        df = df[mask].copy()
        print(f"    粗筛: {n_orig} → {len(df)} 条")

        if len(df) == 0:
            continue

        # 第二步：坐标转换
        o_lons, o_lats = batch_bd09_to_wgs84(df[ox].values, df[oy].values)
        d_lons, d_lats = batch_bd09_to_wgs84(df[dx].values, df[dy].values)
        df['o_lon_wgs'] = o_lons
        df['o_lat_wgs'] = o_lats
        df['d_lon_wgs'] = d_lons
        df['d_lat_wgs'] = d_lats

        # 第三步：精筛（WGS84 坐标下判断是否在研究范围内）
        prepared_polygon = prep(study_polygon)
        in_study = np.array([
            prepared_polygon.contains(Point(o_lons[j], o_lats[j])) or
            prepared_polygon.contains(Point(d_lons[j], d_lats[j]))
            for j in range(len(df))
        ])
        df = df[in_study].copy()
        print(f"    精筛: → {len(df)} 条")

        all_dfs.append(df)

    if all_dfs:
        result = pd.concat(all_dfs, ignore_index=True)
        print(f"  合计: {len(result)} 条")
        return result
    else:
        return pd.DataFrame()


def main():
    print("=" * 60)
    print("Step 5: OD 与通勤数据裁剪")
    print("=" * 60)

    study_polygon = load_study_area()
    bbox = get_bbox_filter(study_polygon)
    out_dir_od = DIRS['od_data']
    out_dir_cm = DIRS['commute']
    fig_dir = DIRS['figures']

    print(f"\n  粗筛范围 (BD-09): lon[{bbox['lon_min']:.3f}, {bbox['lon_max']:.3f}], "
          f"lat[{bbox['lat_min']:.3f}, {bbox['lat_max']:.3f}]")

    # ------------------------------------------------------------------
    # 1. 天尺度 OD 数据
    # ------------------------------------------------------------------
    print("\n[1/3] 处理天尺度 OD 数据 (cf_day)...")
    od_day_pattern = os.path.join(OD_DAY_DIR, OD_DAY_PATTERN)
    od_day = process_od_files(od_day_pattern, 'cf_day', study_polygon, bbox)
    if len(od_day) > 0:
        od_day.to_csv(os.path.join(out_dir_od, "od_day_study_area.csv"),
                      index=False, encoding='utf-8-sig')
        print(f"  ✅ 已保存天尺度 OD: {len(od_day)} 条")

    # ------------------------------------------------------------------
    # 2. 小时 OD 数据
    # ------------------------------------------------------------------
    print("\n[2/3] 处理小时 OD 数据 (cf_hour)...")
    od_hour_pattern = os.path.join(OD_HOUR_DIR, OD_HOUR_PATTERN)
    od_hour = process_od_files(od_hour_pattern, 'cf_hour', study_polygon, bbox)
    if len(od_hour) > 0:
        od_hour.to_csv(os.path.join(out_dir_od, "od_hour_study_area.csv"),
                       index=False, encoding='utf-8-sig')
        print(f"  ✅ 已保存小时 OD: {len(od_hour)} 条")

    # ------------------------------------------------------------------
    # 3. 通勤数据
    # ------------------------------------------------------------------
    print("\n[3/3] 处理通勤数据 (zz_merged)...")
    if os.path.exists(COMMUTE_FILE):
        commute = pd.read_csv(COMMUTE_FILE, sep='\t', dtype=str)
        print(f"  原始通勤记录: {len(commute)}")

        # 坐标列
        ox, oy = '居住地网格中心x坐标', '居住地网格中心y坐标'
        dx, dy = '工作地网格中心x坐标', '工作地网格中心y坐标'
        for col in [ox, oy, dx, dy]:
            commute[col] = pd.to_numeric(commute[col], errors='coerce')
        commute = commute.dropna(subset=[ox, oy, dx, dy])

        # 粗筛
        mask = (
            ((commute[ox] >= bbox['lon_min']) & (commute[ox] <= bbox['lon_max']) &
             (commute[oy] >= bbox['lat_min']) & (commute[oy] <= bbox['lat_max'])) |
            ((commute[dx] >= bbox['lon_min']) & (commute[dx] <= bbox['lon_max']) &
             (commute[dy] >= bbox['lat_min']) & (commute[dy] <= bbox['lat_max']))
        )
        commute = commute[mask].copy()

        # 坐标转换
        o_lons, o_lats = batch_bd09_to_wgs84(commute[ox].values, commute[oy].values)
        d_lons, d_lats = batch_bd09_to_wgs84(commute[dx].values, commute[dy].values)
        commute['o_lon_wgs'], commute['o_lat_wgs'] = o_lons, o_lats
        commute['d_lon_wgs'], commute['d_lat_wgs'] = d_lons, d_lats

        # 精筛
        prepared = prep(study_polygon)
        in_study = np.array([
            prepared.contains(Point(o_lons[j], o_lats[j])) or
            prepared.contains(Point(d_lons[j], d_lats[j]))
            for j in range(len(commute))
        ])
        commute = commute[in_study].copy()

        commute.to_csv(os.path.join(out_dir_cm, "commute_study_area.csv"),
                       index=False, encoding='utf-8-sig')
        print(f"  ✅ 已保存通勤数据: {len(commute)} 条")
    else:
        commute = pd.DataFrame()
        print(f"  ⚠️ 通勤文件不存在: {COMMUTE_FILE}")

    # ------------------------------------------------------------------
    # 可视化
    # ------------------------------------------------------------------
    print("\n正在生成可视化...")
    plot_od_results(od_day, od_hour, commute, study_polygon, fig_dir)

    # 摘要
    print("\n" + "=" * 60)
    print("Step 5 完成 - 摘要")
    print("=" * 60)
    print(f"  天尺度 OD:  {len(od_day):>10,} 条")
    print(f"  小时 OD:    {len(od_hour):>10,} 条")
    print(f"  通勤数据:   {len(commute):>10,} 条")


def plot_od_results(od_day, od_hour, commute, study_polygon, fig_dir):
    """OD 数据可视化"""

    # 加载底图
    study_area = gpd.read_file(os.path.join(DIRS['study_area'], "study_area_buffer.shp"))
    core = gpd.read_file(os.path.join(DIRS['study_area'], "yizhuang_boundary.shp"))
    incident = gpd.read_file(os.path.join(DIRS['study_area'], "incident_point.shp"))
    road_path = os.path.join(DIRS['road_network'], "roads_study_area.shp")
    roads = gpd.read_file(road_path) if os.path.exists(road_path) else None

    fig = plt.figure(figsize=(24, 16))
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3)

    def draw_base(ax):
        study_area.boundary.plot(ax=ax, color='#2196F3', linewidth=1, linestyle='--', alpha=0.4)
        core.boundary.plot(ax=ax, color='#E65100', linewidth=1.5)
        if roads is not None:
            roads.plot(ax=ax, color='#E0E0E0', linewidth=0.15)
        incident.plot(ax=ax, color='red', marker='*', markersize=100, zorder=10)

    # ===== 图1: OD 起点热力图 =====
    ax1 = fig.add_subplot(gs[0, 0])
    draw_base(ax1)
    if len(od_day) > 0 and 'o_lon_wgs' in od_day.columns:
        ax1.hexbin(od_day['o_lon_wgs'].astype(float),
                   od_day['o_lat_wgs'].astype(float),
                   gridsize=60, cmap='YlOrRd', alpha=0.7, mincnt=1)
        plt.colorbar(ax1.collections[-1], ax=ax1, shrink=0.6, label='出行起点密度')
    ax1.set_title('出行起点空间分布（天尺度）', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.2)

    # ===== 图2: OD 终点热力图 =====
    ax2 = fig.add_subplot(gs[0, 1])
    draw_base(ax2)
    if len(od_day) > 0 and 'd_lon_wgs' in od_day.columns:
        ax2.hexbin(od_day['d_lon_wgs'].astype(float),
                   od_day['d_lat_wgs'].astype(float),
                   gridsize=60, cmap='YlGnBu', alpha=0.7, mincnt=1)
        plt.colorbar(ax2.collections[-1], ax=ax2, shrink=0.6, label='出行终点密度')
    ax2.set_title('出行终点空间分布（天尺度）', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.2)

    # ===== 图3: 小时分布 =====
    ax3 = fig.add_subplot(gs[0, 2])
    if len(od_hour) > 0 and '小时' in od_hour.columns:
        od_hour['小时'] = pd.to_numeric(od_hour['小时'], errors='coerce')
        od_hour['数量'] = pd.to_numeric(od_hour['数量'], errors='coerce')
        hourly = od_hour.groupby('小时')['数量'].sum()
        ax3.bar(hourly.index, hourly.values, color='#1976D2', alpha=0.8, edgecolor='white')
        ax3.axvspan(7, 9, alpha=0.15, color='red', label='早高峰')
        ax3.axvspan(17, 19, alpha=0.15, color='orange', label='晚高峰')
        ax3.legend(fontsize=9)
    ax3.set_xlabel('小时', fontsize=11)
    ax3.set_ylabel('出行总量', fontsize=11)
    ax3.set_title('出行时间分布', fontsize=12, fontweight='bold')
    ax3.set_xticks(range(0, 24, 2))

    # ===== 图4: 日期分布 =====
    ax4 = fig.add_subplot(gs[1, 0])
    if len(od_day) > 0 and '日期' in od_day.columns:
        od_day['数量'] = pd.to_numeric(od_day['数量'], errors='coerce')
        daily = od_day.groupby('日期')['数量'].sum()
        ax4.bar(range(len(daily)), daily.values, color='#43A047', alpha=0.8, edgecolor='white')
        ax4.set_xticks(range(len(daily)))
        ax4.set_xticklabels([str(d) for d in daily.index], rotation=45, fontsize=8)
    ax4.set_xlabel('日期')
    ax4.set_ylabel('出行总量')
    ax4.set_title('逐日出行总量', fontsize=12, fontweight='bold')

    # ===== 图5: 通勤方式构成 =====
    ax5 = fig.add_subplot(gs[1, 1])
    if len(commute) > 0:
        mode_cols = ['驾车比例', '地铁比例', '公交比例', '骑行比例', '步行比例']
        existing_cols = [c for c in mode_cols if c in commute.columns]
        if existing_cols:
            commute_num = commute[existing_cols].apply(pd.to_numeric, errors='coerce')
            means = commute_num.mean()
            labels = [c.replace('比例', '') for c in existing_cols]
            colors_mode = ['#D32F2F', '#1565C0', '#2E7D32', '#FF6F00', '#795548']
            wedges, texts, autotexts = ax5.pie(
                means.values, labels=labels, colors=colors_mode[:len(labels)],
                autopct='%1.1f%%', pctdistance=0.8
            )
    ax5.set_title('通勤方式构成', fontsize=12, fontweight='bold')

    # ===== 图6: 通勤流向 =====
    ax6 = fig.add_subplot(gs[1, 2])
    draw_base(ax6)
    if len(commute) > 0 and 'o_lon_wgs' in commute.columns:
        # 采样绘制（避免太密）
        sample = commute.head(min(500, len(commute)))
        for _, row in sample.iterrows():
            try:
                ax6.annotate('', xy=(float(row['d_lon_wgs']), float(row['d_lat_wgs'])),
                            xytext=(float(row['o_lon_wgs']), float(row['o_lat_wgs'])),
                            arrowprops=dict(arrowstyle='->', color='#1976D2', alpha=0.1, lw=0.3))
            except (ValueError, KeyError):
                pass
    ax6.set_title('通勤流向示意（采样）', fontsize=12, fontweight='bold')
    ax6.grid(True, alpha=0.2)

    fig.suptitle('Step 5: OD 与通勤数据处理结果', fontsize=18, fontweight='bold', y=1.01)
    fig_path = os.path.join(fig_dir, "step5_od_commute.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  ✅ 图片已保存至 {fig_path}")


if __name__ == '__main__':
    main()
