"""
run_all.py — 全流程一键运行
=============================
项目目录结构：
  project/
  ├── run_all.py          ← 本文件（项目根目录）
  ├── scripts/
  │   ├── config.py
  │   ├── coord_transform.py
  │   ├── network_router.py
  │   ├── step0_study_area.py
  │   ├── step2_road_network.py
  │   ├── step3_poi_filter.py
  │   ├── step4_population.py
  │   ├── step5_od_clip.py
  │   ├── step6_travel_time.py
  │   ├── step7_subway.py
  │   ├── step8_integration.py
  │   ├── step9_scenario.py
  │   ├── step10_supply_optimization.py
  │   ├── step11_evacuation.py
  │   └── step12_analysis.py
  └── output/

运行顺序：
  0→2→3→4→5→6→7→8→9→11→10→12
  ⚠️ step11 先于 step10：疏散输出就地避难人口 → 物资配送读取

用法：
  python run_all.py                 # 运行全部步骤
  python run_all.py --from 9        # 从 step9 开始
  python run_all.py --only 11 10    # 只运行 step11 和 step10
  python run_all.py --skip 5 6      # 跳过 step5 和 step6
"""
import sys
import os
import time
import argparse
import importlib
import traceback

# 项目根目录和脚本目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

# 把 scripts/ 加入 sys.path，使得 step 脚本能互相 import（如 from config import *）
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# 步骤定义：(步骤编号, 模块名, 描述, 入口函数名)
# 注意执行顺序：step11 排在 step10 之前
STEPS = [
    (0,  'step0_study_area',           '确定研究范围',       'main'),
    (2,  'step2_road_network',         '路网数据处理',       'main'),
    (3,  'step3_poi_filter',           'POI 数据筛选',       'main'),
    (4,  'step4_population',           '人口数据处理',       'main'),
    (5,  'step5_od_clip',              'OD 与通勤数据裁剪',  'main'),
    (6,  'step6_travel_time',          '行程时间矩阵',       'main'),
    (7,  'step7_subway',               '地铁网络处理',       'main'),
    (8,  'step8_integration',          '数据整合与检验',     'main'),
    (9,  'step9_scenario',             '事故场景构建',       'main'),
    (11, 'step11_evacuation',          '疏散优化(ERPG分区)', 'main'),
    (10, 'step10_supply_optimization', '物资配送优化',       'main'),
    (12, 'step12_analysis',            '综合分析与图表',     'main'),
]

STEP_ORDER = [s[0] for s in STEPS]


def run_step(step_num, module_name, description, entry_func):
    """运行单个步骤"""
    print("\n" + "=" * 70)
    print(f"  Step {step_num}: {description}")
    print(f"  模块: scripts/{module_name}.py")
    print("=" * 70)

    t0 = time.time()
    try:
        orig_cwd = os.getcwd()
        os.chdir(SCRIPTS_DIR)

        if module_name in sys.modules:
            del sys.modules[module_name]
        mod = importlib.import_module(module_name)
        func = getattr(mod, entry_func)
        func()

        os.chdir(orig_cwd)
        elapsed = time.time() - t0
        print(f"\n  ✅ Step {step_num} 完成 ({elapsed:.1f}s)")
        return True, elapsed

    except FileNotFoundError as e:
        try: os.chdir(orig_cwd)
        except: pass
        elapsed = time.time() - t0
        print(f"\n  ⚠️ Step {step_num} 文件缺失: {e}")
        return False, elapsed

    except Exception as e:
        try: os.chdir(orig_cwd)
        except: pass
        elapsed = time.time() - t0
        print(f"\n  ❌ Step {step_num} 失败: {e}")
        traceback.print_exc()
        return False, elapsed


def main():
    parser = argparse.ArgumentParser(
        description='应急协同优化全流程运行',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python run_all.py                    全部运行
  python run_all.py --from 9           从 step9 开始
  python run_all.py --only 11 10       只跑疏散+配送
  python run_all.py --only 11 10 12    只跑疏散+配送+分析
  python run_all.py --skip 5 6         跳过 OD 和行程时间
        """)
    parser.add_argument('--from', dest='from_step', type=int, default=None,
                        help='从指定步骤开始运行')
    parser.add_argument('--only', type=int, nargs='+', default=None,
                        help='仅运行指定步骤')
    parser.add_argument('--skip', type=int, nargs='+', default=None,
                        help='跳过指定步骤')
    parser.add_argument('--stop-on-error', action='store_true',
                        help='遇到错误时停止')
    args = parser.parse_args()

    print("=" * 70)
    print("  应急协同优化 — 全流程运行")
    print(f"  项目目录: {PROJECT_ROOT}")
    print(f"  脚本目录: {SCRIPTS_DIR}")
    print("  执行顺序: 0→2→3→4→5→6→7→8→9→11→10→12")
    print("=" * 70)

    if not os.path.isdir(SCRIPTS_DIR):
        print(f"\n  ❌ 脚本目录不存在: {SCRIPTS_DIR}")
        return

    # 筛选步骤
    steps_to_run = list(STEPS)

    if args.only is not None:
        requested = list(args.only)
        # 自动修正：如果同时包含 10 和 11，确保 11 在 10 之前
        if 10 in requested and 11 in requested:
            idx_10 = requested.index(10)
            idx_11 = requested.index(11)
            if idx_10 < idx_11:
                requested[idx_10], requested[idx_11] = requested[idx_11], requested[idx_10]
                print("  ℹ️ 自动调整: step11 → step10 (依赖关系)")
        steps_to_run = []
        for num in requested:
            match = [s for s in STEPS if s[0] == num]
            if match:
                steps_to_run.append(match[0])
            else:
                print(f"  ⚠️ Step {num} 不存在，可选: {STEP_ORDER}")

    elif args.from_step is not None:
        if args.from_step in STEP_ORDER:
            idx = STEP_ORDER.index(args.from_step)
            steps_to_run = STEPS[idx:]
        else:
            print(f"  ⚠️ Step {args.from_step} 不在列表中，可选: {STEP_ORDER}")
            return

    if args.skip is not None:
        steps_to_run = [s for s in steps_to_run if s[0] not in args.skip]

    if not steps_to_run:
        print("\n  没有步骤需要运行")
        return

    print(f"\n  将运行 {len(steps_to_run)} 个步骤:")
    for num, mod, desc, _ in steps_to_run:
        path = os.path.join(SCRIPTS_DIR, f"{mod}.py")
        flag = "✓" if os.path.exists(path) else "✗"
        print(f"    [{flag}] Step {num:2d}: {desc}")

    # 运行
    results = []
    total_t0 = time.time()

    for step_num, module_name, description, entry_func in steps_to_run:
        path = os.path.join(SCRIPTS_DIR, f"{module_name}.py")
        if not os.path.exists(path):
            print(f"\n  ⚠️ 跳过 Step {step_num}: {path} 不存在")
            results.append((step_num, description, False, 0))
            if args.stop_on_error:
                break
            continue

        ok, elapsed = run_step(step_num, module_name, description, entry_func)
        results.append((step_num, description, ok, elapsed))
        if not ok and args.stop_on_error:
            print(f"\n  ⛔ 在 Step {step_num} 停止")
            break

    total_elapsed = time.time() - total_t0

    # 汇总
    print("\n" + "=" * 70)
    print("  运行结果汇总")
    print("=" * 70)
    for num, desc, ok, elapsed in results:
        status = "✅" if ok else "❌"
        print(f"    {status} Step {num:2d}: {desc}  ({elapsed:.1f}s)")
    print("-" * 70)
    n_ok = sum(1 for _, _, ok, _ in results if ok)
    n_fail = sum(1 for _, _, ok, _ in results if not ok)
    print(f"  成功: {n_ok}, 失败: {n_fail}, 总耗时: {total_elapsed:.1f}s")


if __name__ == '__main__':
    main()
