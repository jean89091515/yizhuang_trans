"""
==================== 项目全局配置 ====================
六环太和桥事故应急研究 - 数据准备
修改下方路径为你本机的实际路径后运行各步骤脚本
"""
import os

# ==================== 1. 原始数据路径 ====================

# OSM 路网
OSM_ROAD_SHP = r"/Users/liangwang/12-数据/16-openstreetmap/0original/beijingroaddata.shp"

# POI 数据
POI_FILE = r"/Users/liangwang/12-数据/33-POI数据/POI202206_北京.txt"

# 七普人口数据
# ⚠️ 此路径含特殊字符（【】、|、：），如果报错"No such file"，请：
#   1. 在终端运行下面这行命令确认实际路径：
#      ls /Users/liangwang/12-数据/23-全国七普数据*/*七普*/*分区县*/*.shp
#   2. 把 ls 输出的路径粘贴到下面替换
#   3. 或者把该 shp 及同名的 .shx/.dbf/.prj 文件复制到一个无特殊字符的目录，例如：
#      cp /Users/liangwang/12-数据/23-全国七普数据*/表2*/*分区县*/分年龄* /Users/liangwang/12-数据/census/
#      然后把路径改为 /Users/liangwang/12-数据/census/分年龄、性别的人口_区县等级.shp
CENSUS_SHP = r"/Users/liangwang/12-数据/23-全国七普数据【立方数据】/表2：分年龄、性别的人口- 【七普人口数据|省市县三级】/GIS格式的数据/分区县的数据/分年龄、性别的人口_区县等级.shp"

# 地铁线路数据（shp）
METRO_ROUTES_SHP = r"/Users/liangwang/0-成果转化/01-论文/37-地铁时序数据集/2-数据/metro_routes.shp"
# 地铁站点数据（shp）
METRO_STOPS_SHP = r"/Users/liangwang/0-成果转化/01-论文/37-地铁时序数据集/2-数据/metro_stops_with_opening_years.shp"

# 地块级人口数据
BLOCK_POP_SHP = r"/Volumes/WLSSD990/北京251010_251017百度数据/Block_population/Block_population.shp"

# 亦庄控规界
YIZHUANG_BOUNDARY_SHP = r"/Volumes/WLSSD990/0-百度数据预处理程序/shp/亦庄控规界.shp"

# 百度 OD 数据 (天尺度)
OD_DAY_DIR = r"/Volumes/WLSSD990/北京251010_251017百度数据/lb_bj_od_100_251010_251014_cf_day"
OD_DAY_PATTERN = "lb_bj_100_251010_251014_cf_day_2025*.txt"

# 百度 OD 数据 (小时尺度)
OD_HOUR_DIR = r"/Volumes/WLSSD990/北京251010_251017百度数据/lb_bj_od_100_251010_251014_cf_hour"
OD_HOUR_PATTERN = "lb_bj_100_251010_251014_cf_hour_2025*.txt"

# 通勤合并数据
COMMUTE_FILE = r"/Volumes/WLSSD990/北京251010_251017百度数据/lb_bj_zz_tqfs_100_2510/zz_merged_202510.txt"

# ==================== 2. 输出路径 ====================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

# 各步骤输出子目录
DIRS = {
    "study_area":   os.path.join(OUTPUT_DIR, "0_study_area"),
    "road_network": os.path.join(OUTPUT_DIR, "1_road_network"),
    "poi":          os.path.join(OUTPUT_DIR, "2_poi"),
    "population":   os.path.join(OUTPUT_DIR, "3_population"),
    "od_data":      os.path.join(OUTPUT_DIR, "4_od_data"),
    "commute":      os.path.join(OUTPUT_DIR, "5_commute"),
    "travel_time":  os.path.join(OUTPUT_DIR, "6_travel_time"),
    "subway":       os.path.join(OUTPUT_DIR, "7_subway"),
    "integrated":   os.path.join(OUTPUT_DIR, "8_integrated"),
    "scenario":     os.path.join(OUTPUT_DIR, "9_scenario"),
    "supply_opt":   os.path.join(OUTPUT_DIR, "10_supply_optimization"),
    "evac_opt":     os.path.join(OUTPUT_DIR, "11_evacuation_optimization"),
    "analysis":     os.path.join(OUTPUT_DIR, "12_analysis"),
    "figures":      os.path.join(OUTPUT_DIR, "figures"),
}

# 创建所有目录
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

# ==================== 3. 研究参数 ====================

# 事故中心点 (WGS84) —— 请根据实际情况修改
# 六环太和桥大致位置
INCIDENT_LON = 116.49401419705991
INCIDENT_LAT = 39.73559923848592

# 研究范围缓冲半径 (米)
BUFFER_RADIUS_M = 15000

# 投影坐标系 (UTM 50N，适用于北京)
UTM_CRS = "EPSG:32650"
WGS84_CRS = "EPSG:4326"

# ==================== 4. 道路属性参数 ====================

# 道路默认限速 (km/h)
SPEED_MAP = {
    'motorway': 100, 'motorway_link': 80,
    'trunk': 80,     'trunk_link': 60,
    'primary': 60,   'primary_link': 50,
    'secondary': 50, 'secondary_link': 40,
    'tertiary': 40,  'tertiary_link': 30,
    'residential': 30, 'unclassified': 30,
    'service': 20,    'living_street': 20,
}

# 道路单向通行能力 (pcu/h)
CAPACITY_MAP = {
    'motorway': 6000, 'motorway_link': 3000,
    'trunk': 4500,    'trunk_link': 2000,
    'primary': 3000,  'primary_link': 1500,
    'secondary': 2000,'secondary_link': 1000,
    'tertiary': 1500, 'tertiary_link': 800,
    'residential': 800,'unclassified': 800,
    'service': 400,    'living_street': 400,
}

# 可通行车辆的道路类型
VEHICLE_ROAD_CLASSES = [
    'motorway', 'motorway_link', 'trunk', 'trunk_link',
    'primary', 'primary_link', 'secondary', 'secondary_link',
    'tertiary', 'tertiary_link', 'residential', 'unclassified',
    'living_street', 'service'
]

# BPR 函数参数（用于拥堵下行程时间估算）
BPR_ALPHA = 0.15
BPR_BETA = 4.0

print(f"[config] 项目根目录: {PROJECT_ROOT}")
print(f"[config] 输出目录: {OUTPUT_DIR}")
print(f"[config] 事故中心点: ({INCIDENT_LON}, {INCIDENT_LAT})")

# ==================== 5. 路径验证与自动发现 ====================
import glob

def resolve_path(path, glob_pattern=None, description=""):
    """
    验证路径是否存在，如果不存在则尝试用 glob 模式匹配。
    解决路径中含 【】、|、：等特殊字符导致找不到文件的问题。
    """
    if os.path.exists(path):
        return path

    # 尝试 glob 匹配
    if glob_pattern:
        matches = glob.glob(glob_pattern, recursive=True)
        if matches:
            print(f"  [路径修复] {description}: 原路径不可访问，通过 glob 找到: {matches[0]}")
            return matches[0]

    print(f"  ⚠️ [路径警告] {description}: 文件不存在 → {path}")
    if glob_pattern:
        print(f"     尝试的 glob: {glob_pattern} (也未匹配)")
    print(f"     请手动确认路径，或将文件复制到无特殊字符的目录")
    return path  # 返回原路径，让后续步骤报更明确的错

# 验证关键路径
CENSUS_SHP = resolve_path(
    CENSUS_SHP,
    glob_pattern="/Users/liangwang/12-数据/23-全国七普*/**/分年龄*_区县等级.shp",
    description="七普人口数据"
)

BLOCK_POP_SHP = resolve_path(
    BLOCK_POP_SHP,
    glob_pattern="/Volumes/WLSSD990/北京251010_251017百度数据/Block_population/Block_population.shp",
    description="地块级人口数据"
)

YIZHUANG_BOUNDARY_SHP = resolve_path(
    YIZHUANG_BOUNDARY_SHP,
    description="亦庄控规界"
)

OSM_ROAD_SHP = resolve_path(
    OSM_ROAD_SHP,
    description="OSM路网"
)

POI_FILE = resolve_path(
    POI_FILE,
    description="POI数据"
)

METRO_ROUTES_SHP = resolve_path(
    METRO_ROUTES_SHP,
    description="地铁线路数据"
)

METRO_STOPS_SHP = resolve_path(
    METRO_STOPS_SHP,
    description="地铁站点数据"
)

