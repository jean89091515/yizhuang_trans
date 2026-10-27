<template>
  <div v-if="state.detailOpen && r" class="mask" @click.self="state.detailOpen = false">
    <div class="modal">
      <header>
        <span class="t">计算结果详情</span>
        <div class="tab-group">
          <button v-for="t in tabs" :key="t.k" :class="{ active: tab === t.k }" @click="tab = t.k">{{ t.l }}</button>
        </div>
        <div class="acts">
          <button class="link-btn" @click="download('result')">导出结果 JSON</button>
          <button class="link-btn" @click="download('params')">导出参数 JSON</button>
          <button class="x" @click="state.detailOpen = false">×</button>
        </div>
      </header>
      <div class="body">
        <!-- 疏散 -->
        <template v-if="tab === 'evac'">
          <div v-if="!r.evacuation" class="empty">当前方法未包含人员疏散</div>
          <template v-else>
            <table>
              <thead><tr><th>方案</th><th>疏散/需疏散</th><th>疏散率</th><th>k=1 重伤</th><th>k=2 脆弱</th><th>k=3 一般</th>
                <th v-for="m in MODE_KEYS" :key="m">{{ VEHICLE_MODES[m].name }}(人)</th><th>累计风险(万)</th><th>目标函数 Z</th></tr></thead>
              <tbody>
                <tr v-for="s in EVAC_SCHEMES" :key="s.key" :class="{ sel: state.evacScheme === s.key }" @click="state.evacScheme = s.key">
                  <td>{{ s.label }}</td>
                  <td class="num">{{ f(ev(s.key).evacuated) }} / {{ f(ev(s.key).total) }}</td>
                  <td class="num hi">{{ p(ev(s.key).rate) }}</td>
                  <td class="num" v-for="k in [1, 2, 3]" :key="k">{{ ev(s.key).byClass[k].total ? p(ev(s.key).byClass[k].rate) : '—' }}</td>
                  <td class="num" v-for="m in MODE_KEYS" :key="m">{{ f(ev(s.key).byMode[m].people) }}</td>
                  <td class="num">{{ (ev(s.key).totalRisk / 1e4).toFixed(2) }}</td>
                  <td class="num">{{ (ev(s.key).objective.obj / 1e4).toFixed(1) }} 万</td>
                </tr>
              </tbody>
            </table>
            <div class="chart"><EChart :option="timelineOption" /></div>
            <p class="note">目标函数 Z = 1.0·Z₁(加权疏散时间) + 0.01·Z₂(动态风险暴露) + 100·Z₃(未服务惩罚, P=500)；累计风险即 Z₂。点击表格行可切换地图显示的疏散方案。</p>
          </template>
        </template>

        <!-- 配送 -->
        <template v-if="tab === 'supply'">
          <div v-if="!r.supply" class="empty">当前方法未包含物资配送</div>
          <template v-else>
            <table>
              <thead><tr><th>方案</th><th>完成/总任务</th><th>完成率</th><th>Makespan(min)</th><th>平均送达(min)</th><th>惩罚</th><th>直送</th><th>接力</th>
                <th v-for="c in SUPPLY_KEYS" :key="c">{{ SUPPLY_CATEGORIES[c].name }}<br /><small>完成/准时</small></th></tr></thead>
              <tbody>
                <tr v-for="s in SUPPLY_SCHEMES" :key="s.key" :class="{ sel: state.supplyScheme === s.key }" @click="state.supplyScheme = s.key">
                  <td>{{ s.label }}</td>
                  <td class="num">{{ sp(s.key).completed }} / {{ sp(s.key).totalTasks }}</td>
                  <td class="num hi">{{ p(sp(s.key).completionRate) }}</td>
                  <td class="num">{{ sp(s.key).completed ? sp(s.key).makespan.toFixed(1) : '—' }}</td>
                  <td class="num">{{ sp(s.key).completed ? sp(s.key).avgTimeMin.toFixed(1) : '—' }}</td>
                  <td class="num">{{ f(Math.round(sp(s.key).penalty)) }}</td>
                  <td class="num">{{ sp(s.key).routes.direct }}</td>
                  <td class="num">{{ sp(s.key).routes.relay }}</td>
                  <td class="num" v-for="c in SUPPLY_KEYS" :key="c">{{ sp(s.key).byCategory[c].completed }}/{{ sp(s.key).byCategory[c].total }} · {{ sp(s.key).byCategory[c].onTimeRate === null ? '—' : p(sp(s.key).byCategory[c].onTimeRate, 0) }}</td>
                </tr>
              </tbody>
            </table>
            <h4>「{{ sp(state.supplyScheme).label }}」调度明细（{{ sp(state.supplyScheme).schedule.length }} 项）</h4>
            <div class="scroll">
              <table class="small">
                <thead><tr><th>#</th><th>物资类别</th><th>数量</th><th>车辆</th><th>供应点</th><th>中转站</th><th>需求点</th><th>出发</th><th>送达</th><th>时间窗</th></tr></thead>
                <tbody>
                  <tr v-for="x in sortedSchedule" :key="x.taskId">
                    <td class="num">{{ x.taskId }}</td>
                    <td><i class="cat" :style="{ background: SUPPLY_CATEGORIES[x.cat].color }"></i>{{ SUPPLY_CATEGORIES[x.cat].name }}</td>
                    <td class="num">{{ x.qty }}</td><td>{{ x.vehicle }}{{ x.vehicleType === 'drone' ? '（无人机）' : '' }}</td>
                    <td>{{ x.supply }}</td><td>{{ x.relay || '—' }}</td><td>{{ x.demand }}</td>
                    <td class="num">{{ x.departure.toFixed(1) }}</td>
                    <td class="num" :class="{ late: x.arrival > x.deadline }">{{ x.arrival.toFixed(1) }}</td>
                    <td class="num">{{ x.deadline }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </template>

        <!-- 分区与人口 -->
        <template v-if="tab === 'zones'">
          <table>
            <thead><tr><th>分区</th><th>人口</th><th>地块数</th><th>疏散规则（k=1/2/3）</th><th>就地避难（k=1/2/3）</th></tr></thead>
            <tbody>
              <tr v-for="z in ['erpg3', 'erpg2', 'erpg1']" :key="z">
                <td>{{ ZONE_NAMES[z] }}</td>
                <td class="num">{{ f(r.zones.populations[z].total) }}</td>
                <td class="num">{{ r.zones.populations[z].blocks }}</td>
                <td>{{ rule(z) }}</td>
                <td class="num">{{ [1, 2, 3].map((k) => f(r.zones.shelterInPlace[z][k])).join(' / ') }}</td>
              </tr>
            </tbody>
          </table>
          <div class="kv">
            <span>需主动疏散 <b class="num">{{ f(r.zones.evacDemand) }}</b> 人（k=1 {{ f(r.zones.byClassDemand[1]) }}，k=2 {{ f(r.zones.byClassDemand[2]) }}，k=3 {{ f(r.zones.byClassDemand[3]) }}）</span>
            <span>就地避难 <b class="num">{{ f(r.zones.shelterInPlaceTotal) }}</b> 人</span>
            <span>圆形统计：1 km {{ f(r.zones.circles.r1000) }}，3 km {{ f(r.zones.circles.r3000) }}，5 km {{ f(r.zones.circles.r5000) }}</span>
            <span>分区方式：{{ r.zones.mode === 'buffered' ? `等值线外扩（${r.zones.buffers.erpg3}/${r.zones.buffers.erpg2}/${r.zones.buffers.erpg1} m）` : '原始等值线' }}；人口口径：{{ r.zones.populationMode === 'intersect' ? '地块相交（论文口径）' : '面积加权' }}</span>
          </div>
          <h4 v-if="r.evacuation">疏散起点（{{ r.evacuation.origins.length }}）</h4>
          <div class="scroll" v-if="r.evacuation">
            <table class="small">
              <thead><tr><th>起点</th><th>分区</th><th>距事故点(m)</th><th>扇区人口</th><th>k=1</th><th>k=2</th><th>k=3</th><th>风险暴露 ρ(mg/m³)</th></tr></thead>
              <tbody><tr v-for="o in r.evacuation.origins" :key="o.id"><td>{{ o.name }}</td><td>{{ o.zone.toUpperCase() }}</td><td class="num">{{ f(o.distM) }}</td><td class="num">{{ f(o.sectorPop) }}</td>
                <td class="num">{{ o.population[1] }}</td><td class="num">{{ o.population[2] }}</td><td class="num">{{ o.population[3] }}</td><td class="num">{{ o.rho.toFixed(2) }}</td></tr></tbody>
            </table>
          </div>
          <p class="note" v-if="r.zones.populationApproximate">注：默认人口数据由论文 Step4 人口分布图反演并按 Step11 分区人口标定，为近似数据；请用 tools/export_platform_data.py 由原始地块人口生成真实数据替换。</p>
        </template>

        <!-- 论文对照 -->
        <template v-if="tab === 'paper'">
          <div class="banner" :class="{ warn: !isBase }">{{ isBase ? '当前为论文基准场景（太和桥 · 二级西南风 3.0 m/s · D 类 · 5 kg/min），可与论文结果直接对照。' : '当前场景与论文基准不同，以下论文数值仅供参考。' }}</div>
          <table>
            <thead><tr><th>指标</th><th>平台计算</th><th>论文（Step9–12 输出）</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="row in paperRows" :key="row[0]"><td>{{ row[0] }}</td><td class="num hi">{{ row[1] }}</td><td class="num">{{ row[2] }}</td><td class="muted">{{ row[3] }}</td></tr>
            </tbody>
          </table>
          <p class="note">差异主要来源：① 默认数据无真实路网，行程时间采用几何近似模型（接入导出的 road_network.json 后改为 Dijkstra）；② 人口栅格为反演近似；③ 疏散起点取分区扇区人口重心（论文为固定偏移点）；④ 风险暴露 ρ 采用分区阈值浓度与局部平均浓度取大，并随泄漏时长衰减。</p>
        </template>

        <!-- 日志 -->
        <template v-if="tab === 'log'">
          <div class="console"><div v-for="(l, i) in r.log" :key="i" :class="l.level"><span class="ts">[{{ l.t.toFixed(3) }}s]</span> {{ l.msg }}</div></div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import EChart from './EChart.vue'
import { state, result, staticData } from '../store.js'
import { EVAC_SCHEMES, SUPPLY_SCHEMES, MODE_KEYS, VEHICLE_MODES, SUPPLY_CATEGORIES, SUPPLY_KEYS, ZONE_NAMES, EVAC_RULES } from '../engine/index.js'

const tabs = [
  { k: 'evac', l: '疏散方案' }, { k: 'supply', l: '配送方案' }, { k: 'zones', l: '分区与人口' }, { k: 'paper', l: '论文对照' }, { k: 'log', l: '计算日志' },
]
const tab = ref('evac')
const r = computed(() => result.value)
const ev = (k) => r.value.evacuation.schemes[k]
const sp = (k) => r.value.supply.schemes[k]
const f = (v) => (v ?? 0).toLocaleString()
const p = (v, d = 1) => (v === null || v === undefined ? '—' : (v * 100).toFixed(d) + '%')
const rule = (z) => [1, 2, 3].map((k) => (EVAC_RULES[z][k] ? '疏散' : '就地')).join(' / ')
const sortedSchedule = computed(() => [...sp(state.supplyScheme).schedule].sort((a, b) => a.arrival - b.arrival))

const timelineOption = computed(() => {
  const colors = ['#4fd2ff', '#4cff9a', '#ffd23f', '#ff8a3d', '#c77dff']
  return {
    color: colors,
    grid: { left: 60, right: 20, top: 34, bottom: 30 },
    legend: { top: 0, textStyle: { color: '#cfe6ff' } },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(6,22,44,0.92)', borderColor: '#4fd2ff', textStyle: { color: '#fff' } },
    xAxis: { type: 'value', name: 'min', max: r.value.params.evacuation.Tmax, axisLabel: { color: '#8fb3d9' }, splitLine: { show: false } },
    yAxis: { type: 'value', name: '待疏散人数', axisLabel: { color: '#8fb3d9' }, nameTextStyle: { color: '#8fb3d9' }, splitLine: { lineStyle: { color: 'rgba(143,179,217,0.12)' } } },
    series: EVAC_SCHEMES.map((s) => ({ name: s.label, type: 'line', step: 'end', symbol: 'none', data: ev(s.key).timeline.map((x) => [x.t, x.remaining]) })),
  }
})

const isBase = computed(() => {
  const q = r.value.params
  return q.siteId === 'taihe' && q.windSpeed === 3 && q.windDir === 225 && q.stability === 'D' && q.leakRateKgMin === 5
})
const paperRows = computed(() => {
  const ref = staticData.value?.reference
  if (!ref) return []
  const x = r.value
  const rows = [
    ['ERPG-2 警戒区人口', f(x.zones.populations.erpg2.total), f(ref.erpg_zone_populations.erpg2), '地块相交口径'],
    ['ERPG-1 影响区人口', f(x.zones.populations.erpg1.total), f(ref.erpg_zone_populations.erpg1), '地块相交口径'],
    ['需主动疏散人口', f(x.zones.evacDemand), f(13830), 'ERPG-2 k1+k2、ERPG-1 k1'],
    ['道路封闭比例', p(x.roads.ratio), p(ref.resilience.structural.road_closure_ratio), '1 km / 5 km 道路长度'],
  ]
  if (x.evacuation) {
    const m = [['all', 'baseline'], ['no_subway', 'no_subway'], ['no_heli', 'no_helicopter'], ['strict', 'strict_priority']]
    for (const [a, b] of m) rows.push([`疏散率 · ${ev(a).label}`, p(ev(a).rate), p(ref.evacuation[b].evac_rate), `${f(ev(a).evacuated)} vs ${f(ref.evacuation[b].evacuated)} 人`])
    rows.push(['k=2 脆弱群体疏散率', p(ev('all').byClass[2].rate), '100.0%', '分区策略疏散增益'])
    rows.push(['k=1 重伤疏散率', p(ev('all').byClass[1].rate), p(ref.evacuation_sensitivity_ambulance.find((s) => s.n_ambulances === 15)?.critical_evac_rate), '受救护车/直升机运力约束'])
  }
  if (x.supply) {
    const m = [['truck_only', 'truck_only'], ['coordinated', 'coordinated']]
    for (const [a, b] of m) {
      rows.push([`配送完成 · ${sp(a).label}`, `${sp(a).completed}/${sp(a).totalTasks}`, `${ref.supply[b].completed_tasks}/${ref.supply[b].total_tasks}`, ''])
      rows.push([`Makespan · ${sp(a).label}`, `${sp(a).makespan.toFixed(1)} min`, `${ref.supply[b].makespan_min.toFixed(1)} min`, '无路网时为几何近似行程时间'])
    }
    rows.push(['生命救援准时率（协同）', p(sp('coordinated').lifeOnTimeRate, 0), p(ref.supply.coordinated.by_category.life_rescue.on_time_rate, 0), '30 min 硬时间窗'])
    rows.push(['接力任务数（协同）', sp('coordinated').routes.relay, ref.supply.coordinated.route_types.relay, ''])
  }
  return rows
})

function download(kind) {
  const obj = kind === 'result' ? r.value : r.value.params
  const blob = new Blob([JSON.stringify(obj, null, kind === 'result' ? 0 : 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = kind === 'result' ? `emergency_sim_result_${Date.now()}.json` : 'emergency_sim_params.json'
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}
</script>

<style scoped>
.mask { position: absolute; inset: 0; background: rgba(0, 6, 16, 0.55); display: grid; place-items: center; pointer-events: auto; z-index: 20; }
.modal {
  width: 1280px;
  height: 780px;
  display: flex;
  flex-direction: column;
  background: rgba(5, 18, 38, 0.97);
  border: 1px solid rgba(79, 210, 255, 0.6);
  box-shadow: 0 0 40px rgba(47, 123, 255, 0.4);
}
header { display: flex; align-items: center; gap: 18px; padding: 12px 18px; border-bottom: 1px solid rgba(79, 190, 255, 0.3); background: linear-gradient(90deg, rgba(47, 123, 255, 0.3), transparent); }
.t { font-size: 19px; font-weight: 700; color: #fff; letter-spacing: 2px; }
.acts { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.x { background: none; border: none; color: var(--text-2); font-size: 26px; cursor: pointer; line-height: 1; }
.body { flex: 1; overflow-y: auto; padding: 14px 18px 18px; user-select: text; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; font-weight: 600; color: var(--text-2); padding: 7px 8px; border-bottom: 1px solid rgba(79, 190, 255, 0.35); background: rgba(47, 123, 255, 0.12); position: sticky; top: 0; }
td { padding: 7px 8px; border-bottom: 1px solid rgba(79, 190, 255, 0.12); color: var(--text-1); }
tbody tr { cursor: pointer; }
tbody tr:hover { background: rgba(47, 123, 255, 0.12); }
tbody tr.sel { background: rgba(79, 210, 255, 0.16); }
td.hi { color: #fff; font-weight: 700; }
td.late { color: var(--red); }
td.muted { color: var(--text-3); }
table.small { font-size: 12px; }
table.small td, table.small th { padding: 5px 6px; }
.scroll { max-height: 300px; overflow-y: auto; border: 1px solid rgba(79, 190, 255, 0.15); }
h4 { margin: 16px 0 8px; color: #fff; font-size: 14px; }
.chart { height: 240px; margin-top: 12px; }
.note { margin-top: 10px; font-size: 12px; color: var(--text-3); line-height: 1.6; }
.kv { display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 12px 0; font-size: 13px; color: var(--text-2); }
.kv b { color: #fff; }
.cat { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
.banner { padding: 8px 12px; margin-bottom: 10px; font-size: 13px; color: var(--lime); background: rgba(76, 255, 154, 0.08); border-left: 3px solid var(--lime); }
.banner.warn { color: var(--yellow); background: rgba(255, 210, 63, 0.08); border-color: var(--yellow); }
.empty { padding: 60px; text-align: center; color: var(--text-3); }
.console { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; line-height: 1.7; color: #9fc6ec; }
.console .warn { color: var(--yellow); }
.console .success { color: var(--lime); }
.ts { color: var(--text-3); }
</style>
