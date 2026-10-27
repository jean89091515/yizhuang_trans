"""
BD09坐标转WGS84坐标转换程序
支持三种数据格式：
  1. cf_day (日OD数据)
  2. cf_hour (小时OD数据)
  3. zz_tqfs (职住通勤方式数据)

使用方法：直接修改下方 input_file 和 output_file 路径，然后运行 python transform.py
"""

import os
import math

# ==================== 配置区域 ====================
# 修改这里的输入输出文件路径
input_file = r"./sampleData/lb_bj_zz_tqfs_100_2510_202510sp.txt"
output_file = r"./sampleData/lb_bj_zz_tqfs_100_2510_202510sp_wgs84.txt"
# ==================================================

# --- BD09 -> GCJ02 -> WGS84 坐标转换 ---
PI = math.pi
A = 6378245.0  # 长半轴
EE = 0.00669342162296594323  # 偏心率平方
X_PI = PI * 3000.0 / 180.0


def bd09_to_gcj02(bd_lon, bd_lat):
    x = bd_lon - 0.0065
    y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    gcj_lon = z * math.cos(theta)
    gcj_lat = z * math.sin(theta)
    return gcj_lon, gcj_lat


def _transform_lat(lon, lat):
    ret = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat + \
          0.1 * lon * lat + 0.2 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * PI) + 20.0 *
            math.sin(2.0 * lon * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * PI) + 40.0 *
            math.sin(lat / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * PI) + 320.0 *
            math.sin(lat * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(lon, lat):
    ret = 300.0 + lon + 2.0 * lat + 0.1 * lon * lon + \
          0.1 * lon * lat + 0.1 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * PI) + 20.0 *
            math.sin(2.0 * lon * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lon * PI) + 40.0 *
            math.sin(lon / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lon / 12.0 * PI) + 300.0 *
            math.sin(lon / 30.0 * PI)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(gcj_lon, gcj_lat):
    d_lat = _transform_lat(gcj_lon - 105.0, gcj_lat - 35.0)
    d_lon = _transform_lon(gcj_lon - 105.0, gcj_lat - 35.0)
    rad_lat = gcj_lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
    d_lon = (d_lon * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * PI)
    wgs_lat = gcj_lat - d_lat
    wgs_lon = gcj_lon - d_lon
    return wgs_lon, wgs_lat


def bd09_to_wgs84(bd_lon, bd_lat):
    gcj_lon, gcj_lat = bd09_to_gcj02(bd_lon, bd_lat)
    return gcj02_to_wgs84(gcj_lon, gcj_lat)


def detect_file_type(header):
    """根据表头自动检测文件类型"""
    cols = header.strip().split('\t')
    if '小时' in cols:
        return 'cf_hour'
    elif '驾车比例' in cols:
        return 'zz_tqfs'
    else:
        return 'cf_day'


def get_coord_columns(file_type):
    """
    返回需要转换的坐标列索引 (x列, y列) 的列表
    """
    if file_type == 'cf_day':
        # 起点x(3), 起点y(4), 终点x(7), 终点y(8)
        return [(3, 4), (7, 8)]
    elif file_type == 'cf_hour':
        # 起点x(4), 起点y(5), 终点x(8), 终点y(9)
        return [(4, 5), (8, 9)]
    elif file_type == 'zz_tqfs':
        # 居住地x(3), 居住地y(4), 工作地x(7), 工作地y(8)
        return [(3, 4), (7, 8)]
    return []


def process_file(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if not lines:
        print("文件为空！")
        return

    header = lines[0]
    file_type = detect_file_type(header)
    coord_cols = get_coord_columns(file_type)

    print(f"检测到文件类型: {file_type}")
    print(f"需要转换的坐标列对: {coord_cols}")

    output_lines = [header]
    converted = 0

    for line in lines[1:]:
        line = line.rstrip('\n')
        if not line.strip():
            continue
        parts = line.split('\t')

        for x_idx, y_idx in coord_cols:
            try:
                bd_lon = float(parts[x_idx])
                bd_lat = float(parts[y_idx])
                wgs_lon, wgs_lat = bd09_to_wgs84(bd_lon, bd_lat)
                parts[x_idx] = f"{wgs_lon:.8f}"
                parts[y_idx] = f"{wgs_lat:.8f}"
            except (ValueError, IndexError) as e:
                print(f"警告: 第{converted+2}行转换失败: {e}")

        output_lines.append('\t'.join(parts) + '\n')
        converted += 1

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)

    print(f"转换完成！共处理 {converted} 行数据")
    print(f"输出文件: {output_path}")


if __name__ == '__main__':
    if not os.path.exists(input_file):
        print(f"错误: 输入文件不存在 -> {input_file}")
        print("请修改脚本顶部的 input_file 路径")
    else:
        process_file(input_file, output_file)