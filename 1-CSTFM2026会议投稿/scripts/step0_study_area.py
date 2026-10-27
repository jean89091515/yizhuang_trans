"""
Step 0: 确定研究范围
===================
功能：
  1. 读取亦庄控规界 shapefile 作为核心研究区域
  2. 生成 15km 缓冲区作为扩展研究范围
  3. 标注事故中心点
  4. 可视化输出
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from shapely.geometry import Point
import numpy as np
from config import *

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def main():
    print("=" * 60)
    print("Step 0: 确定研究范围")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. 读取亦庄控规界
    # ------------------------------------------------------------------
    print("\n[1/4] 读取亦庄控规界...")
    boundary = gpd.read_file(YIZHUANG_BOUNDARY_SHP)
    print(f"  原始坐标系: {boundary.crs}")
    print(f"  要素数量: {len(boundary)}")
    print(f"  范围: {boundary.total_bounds}")

    # 统一转为 WGS84
    if boundary.crs is None:
        print("  ⚠️ 无坐标系信息，假设为 WGS84")
        boundary = boundary.set_crs(WGS84_CRS)
    elif boundary.crs != WGS84_CRS:
        boundary = boundary.to_crs(WGS84_CRS)
        print(f"  已转换为 WGS84")

    # 合并为单个多边形
    study_core = boundary.dissolve()
    core_polygon = study_core.geometry.values[0]
    print(f"  核心研究区域面积: {study_core.to_crs(UTM_CRS).geometry.area.values[0] / 1e6:.2f} km²")

    # ------------------------------------------------------------------
    # 2. 创建事故中心点
    # ------------------------------------------------------------------
    print("\n[2/4] 创建事故中心点...")
    incident_point = Point(INCIDENT_LON, INCIDENT_LAT)
    incident_gdf = gpd.GeoDataFrame(
        {'name': ['六环太平桥事故点'], 'type': ['incident']},
        geometry=[incident_point], crs=WGS84_CRS
    )
    print(f"  事故点坐标: ({INCIDENT_LON}, {INCIDENT_LAT})")

    # ------------------------------------------------------------------
    # 3. 创建 15km 缓冲区
    # ------------------------------------------------------------------
    print("\n[3/4] 创建 15km 缓冲区...")
    # 以事故点为中心创建缓冲区
    incident_proj = incident_gdf.to_crs(UTM_CRS)
    buffer_proj = incident_proj.geometry.buffer(BUFFER_RADIUS_M)
    buffer_gdf = gpd.GeoDataFrame(geometry=buffer_proj, crs=UTM_CRS).to_crs(WGS84_CRS)
    buffer_polygon = buffer_gdf.geometry.values[0]
    print(f"  缓冲区面积: {buffer_gdf.to_crs(UTM_CRS).geometry.area.values[0] / 1e6:.2f} km²")

    # 同时以核心区域边界创建缓冲区
    core_proj = study_core.to_crs(UTM_CRS)
    core_buffer_proj = core_proj.geometry.buffer(BUFFER_RADIUS_M)
    core_buffer_gdf = gpd.GeoDataFrame(geometry=core_buffer_proj, crs=UTM_CRS).to_crs(WGS84_CRS)

    # 最终研究范围 = 两个缓冲区的并集
    study_area_polygon = buffer_polygon.union(core_buffer_gdf.geometry.values[0])
    study_area_gdf = gpd.GeoDataFrame(
        {'name': ['研究范围']}, geometry=[study_area_polygon], crs=WGS84_CRS
    )

    # ------------------------------------------------------------------
    # 4. 保存
    # ------------------------------------------------------------------
    print("\n[4/4] 保存文件...")
    out_dir = DIRS['study_area']

    study_core.to_file(os.path.join(out_dir, "yizhuang_boundary.shp"), encoding='utf-8')
    study_area_gdf.to_file(os.path.join(out_dir, "study_area_buffer.shp"), encoding='utf-8')
    incident_gdf.to_file(os.path.join(out_dir, "incident_point.shp"), encoding='utf-8')
    buffer_gdf.to_file(os.path.join(out_dir, "incident_buffer_15km.shp"), encoding='utf-8')

    print(f"  ✅ 已保存至 {out_dir}")

    # ------------------------------------------------------------------
    # 可视化
    # ------------------------------------------------------------------
    print("\n正在生成可视化...")

    fig, axes = plt.subplots(1, 2, figsize=(20, 10))

    # ----- 左图：全局视角 -----
    ax1 = axes[0]
    study_area_gdf.boundary.plot(ax=ax1, color='#2196F3', linewidth=2,
                                  linestyle='--', label='15km 缓冲区（研究范围）')
    study_core.plot(ax=ax1, color='#FF9800', alpha=0.4, edgecolor='#E65100',
                    linewidth=2, label='亦庄控规界（核心区域）')
    incident_gdf.plot(ax=ax1, color='red', marker='*', markersize=200,
                      zorder=10, label='事故点（六环太平桥）')

    # 添加距离圈
    for r_km in [5, 10, 15]:
        circle = incident_proj.geometry.buffer(r_km * 1000)
        circle_wgs = gpd.GeoDataFrame(geometry=circle, crs=UTM_CRS).to_crs(WGS84_CRS)
        circle_wgs.boundary.plot(ax=ax1, color='gray', linewidth=0.5, linestyle=':')
        # 标注距离
        bounds = circle_wgs.total_bounds
        ax1.text(bounds[2] + 0.005, (bounds[1] + bounds[3]) / 2,
                f'{r_km}km', fontsize=8, color='gray', va='center')

    ax1.set_title('研究范围总览', fontsize=16, fontweight='bold')
    ax1.set_xlabel('经度 (°E)', fontsize=12)
    ax1.set_ylabel('纬度 (°N)', fontsize=12)
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, alpha=0.3)

    # ----- 右图：核心区域放大 -----
    ax2 = axes[1]
    study_core.plot(ax=ax2, color='#FF9800', alpha=0.3, edgecolor='#E65100', linewidth=2)
    study_core.boundary.plot(ax=ax2, color='#E65100', linewidth=2)
    incident_gdf.plot(ax=ax2, color='red', marker='*', markersize=300, zorder=10)

    # 放大到核心区域范围
    core_bounds = study_core.total_bounds
    padding = 0.02
    ax2.set_xlim(core_bounds[0] - padding, core_bounds[2] + padding)
    ax2.set_ylim(core_bounds[1] - padding, core_bounds[3] + padding)

    ax2.set_title('亦庄核心区域放大', fontsize=16, fontweight='bold')
    ax2.set_xlabel('经度 (°E)', fontsize=12)
    ax2.set_ylabel('纬度 (°N)', fontsize=12)
    ax2.grid(True, alpha=0.3)

    # 添加面积统计文本
    core_area = study_core.to_crs(UTM_CRS).geometry.area.values[0] / 1e6
    buffer_area = study_area_gdf.to_crs(UTM_CRS).geometry.area.values[0] / 1e6
    info_text = (f"核心区域面积: {core_area:.1f} km²\n"
                 f"研究范围面积: {buffer_area:.1f} km²\n"
                 f"缓冲半径: {BUFFER_RADIUS_M/1000:.0f} km")
    ax2.text(0.02, 0.98, info_text, transform=ax2.transAxes,
             fontsize=10, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    plt.tight_layout()
    fig_path = os.path.join(DIRS['figures'], "step0_study_area.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  ✅ 图片已保存至 {fig_path}")

    # 打印摘要
    print("\n" + "=" * 60)
    print("Step 0 完成 - 摘要")
    print("=" * 60)
    print(f"  核心区域（亦庄控规界）: {core_area:.1f} km²")
    print(f"  研究范围（含15km缓冲）: {buffer_area:.1f} km²")
    print(f"  事故中心点: ({INCIDENT_LON}°E, {INCIDENT_LAT}°N)")
    print(f"  核心区域范围: [{core_bounds[0]:.4f}, {core_bounds[1]:.4f}] - [{core_bounds[2]:.4f}, {core_bounds[3]:.4f}]")


if __name__ == '__main__':
    main()
