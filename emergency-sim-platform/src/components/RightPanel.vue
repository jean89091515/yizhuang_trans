<template>
  <aside class="right" :class="{ collapsed: state.rightCollapsed }">
    <div class="inner">
      <!-- 优化结果 -->
      <div class="panel-title">优化结果
        <div class="extra">
          <div class="tab-group">
            <button :class="{ active: tab === 'evac' }" @click="tab = 'evac'">人员疏散</button>
            <button :class="{ active: tab === 'supply' }" @click="tab = 'supply'">物资配送</button>
          </div>
          <button class="link-btn" :disabled="!result" @click="state.detailOpen = true">详情 ›</button>
        </div>
      </div>
      <div v-if="cols" class="cols">
        <div class="col" v-for="(c, ci) in cols" :key="c.title">
          <div class="col-title">{{ c.title }}</div>
          <div
            v-for="row in c.rows" :key="row.key" class="item" :class="{ sel: row.key === selectedKey, dim: row.value === null }"
            @click="select(row.key)" :title="`点击在地图上查看「${row.label}」`">
            <div class="line">
              <span class="dot" :class="ci ? 'g' : 'b'"></span>
              <span class="name">{{ row.label }}</span>
              <span class="v num">{{ row.text }}</span>
            </div>
            <div class="track"><i :class="ci ? 'g' : 'b'" :style="{ width: row.pct + '%' }"></i></div>
          </div>
        </div>
      </div>
      <div v-else class="empty">{{ state.running ? '计算中…' : tab === 'evac' ? '当前方法未包含人员疏散' : '当前方法未包含物资配送' }}</div>

      <!-- 可靠性评估 -->
      <div class="panel-title">可靠性评估
        <div class="extra"><span class="hint">{{ radarHint }}</span></div>
      </div>
      <div class="radar">
        <EChart v-if="radarOption" :option="radarOption" />
      </div>

      <!-- 关键指标 -->
      <div class="kpis" v-if="result">
        <div class="kpi"><b class="num">{{ fmt(result.zones.evacDemand) }}</b><span>需疏散人口</span></div>
        <div class="kpi"><b class="num">{{ fmtW(result.zones.shelterInPlaceTotal) }}</b><span>就地避难(万人)</span></div>
        <div class="kpi"><b class="num">{{ result.supply ? result.supply.taskCount : '—' }}</b><span>配送任务(项)</span></div>
        <div class="kpi" :title="result.roads.approx ? '无路网数据，按太和桥道路长度剖面近似' : ''"><b class="num">{{ result.roads.approx ? '≈' : '' }}{{ result.roads.closedKm.toFixed(1) }}</b><span>封闭道路(km)</span></div>
      </div>
    </div>
    <button class="collapse" @click="state.rightCollapsed = !state.rightCollapsed">
      <svg viewBox="0 0 8 12"><path :d="state.rightCollapsed ? 'M6 1L1 6l5 5' : 'M2 1l5 5-5 5'" /></svg>
      <span>{{ state.rightCollapsed ? '展开' : '收起' }}</span>
    </button>
  </aside>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import EChart from './EChart.vue'
import { state, result, resilience } from '../store.js'
import { SUPPLY_SCHEMES } from '../engine/index.js'

const tab = ref('evac')
watch(() => state.view, (v) => { if (v === 'supply') tab.value = 'supply'; if (v === 'evac') tab.value = 'evac' })

const fmt = (v) => (v ?? 0).toLocaleString()
const fmtW = (v) => ((v ?? 0) / 1e4).toFixed(1)
const EVAC_ORDER = [
  ['double_amb', '双倍救护车'], ['no_subway', '无地铁'], ['no_heli', '无直升机'], ['all', '全部资源'],
]

const selectedKey = computed(() => (tab.value === 'evac' ? state.evacScheme : state.supplyScheme))
function select(key) {
  if (tab.value === 'evac') state.evacScheme = key
  else state.supplyScheme = key
}

function pctRows(rows, max) {
  const m = max ?? Math.max(...rows.map((r) => r.value ?? 0), 1e-9)
  return rows.map((r) => ({ ...r, pct: r.value === null ? 0 : Math.max(2, Math.min(100, (r.value / m) * 100)) }))
}

const cols = computed(() => {
  const r = result.value
  if (!r) return null
  if (tab.value === 'evac') {
    const ev = r.evacuation?.schemes
    if (!ev) return null
    const rate = EVAC_ORDER.map(([k, l]) => ({ key: k, label: l, value: ev[k].rate * 100, text: (ev[k].rate * 100).toFixed(1) }))
    const risk = EVAC_ORDER.map(([k, l]) => ({ key: k, label: l, value: ev[k].totalRisk / 1e4, text: (ev[k].totalRisk / 1e4).toFixed(1) }))
    return [
      { title: '疏散完成率对比（%）', rows: pctRows(rate, 100) },
      { title: '累计风险对比（万）', rows: pctRows(risk) },
    ]
  }
  const sp = r.supply?.schemes
  if (!sp) return null
  const short = { truck_only: '纯货车', coordinated: '货车+无人机', coord_double: '加倍无人机', drone_only: '纯无人机' }
  const comp = SUPPLY_SCHEMES.map(({ key }) => ({ key, label: short[key], value: sp[key].completionRate * 100, text: (sp[key].completionRate * 100).toFixed(1) }))
  const mk = SUPPLY_SCHEMES.map(({ key }) => ({ key, label: short[key], value: sp[key].completed ? sp[key].makespan : null, text: sp[key].completed ? sp[key].makespan.toFixed(1) : '—' }))
  return [
    { title: '配送完成率对比（%）', rows: pctRows(comp, 100) },
    { title: '最大完成时间（min）', rows: pctRows(mk) },
  ]
})

const radarHint = computed(() => {
  if (!result.value) return ''
  const s = SUPPLY_SCHEMES.find((x) => x.key === state.supplyScheme)?.label?.replace('方案', '') || ''
  const e = { all: '全部资源', double_amb: '双倍救护车', no_subway: '无地铁', no_heli: '无直升机', strict: '严格优先级' }[state.evacScheme]
  return `${s} · ${e}`
})

const radarOption = computed(() => {
  const rs = resilience.value
  if (!rs) return null
  const vals = rs.radar.map((d) => (d.value === null ? 0 : +(d.value * 100).toFixed(1)))
  return {
    tooltip: {
      backgroundColor: 'rgba(6,22,44,0.92)', borderColor: '#4fd2ff', textStyle: { color: '#fff' },
      formatter: () => rs.radar.map((d) => `${d.name}：${d.value === null ? '—' : (d.value * 100).toFixed(1) + '%'}${d.note ? `<br/><span style="color:#8fb3d9;font-size:12px">${d.note}</span>` : ''}`).join('<br/>'),
    },
    radar: {
      center: ['50%', '54%'],
      radius: '64%',
      startAngle: 90,
      splitNumber: 4,
      indicator: rs.radar.map((d) => ({ name: d.name, max: 100 })),
      axisName: { color: '#e8f4ff', fontSize: 14, formatter: (n) => n },
      axisNameGap: 22,
      splitArea: { areaStyle: { color: ['rgba(25,211,197,0.04)', 'rgba(25,211,197,0.08)', 'rgba(25,211,197,0.12)', 'rgba(25,211,197,0.18)'] } },
      splitLine: { lineStyle: { color: 'rgba(79,210,255,0.35)' } },
      axisLine: { lineStyle: { color: 'rgba(79,210,255,0.35)' } },
    },
    series: [{
      type: 'radar',
      symbol: 'circle',
      symbolSize: 7,
      data: [{
        value: vals,
        label: { show: true, color: '#fff', fontSize: 12, formatter: (p) => `${p.value}%`, distance: 4 },
        lineStyle: { color: '#19d3c5', width: 2 },
        itemStyle: { color: '#e9fffd', borderColor: '#19d3c5', borderWidth: 2 },
        areaStyle: { color: { type: 'radial', x: 0.5, y: 0.5, r: 0.7, colorStops: [{ offset: 0, color: 'rgba(25,211,197,0.25)' }, { offset: 1, color: 'rgba(25,211,197,0.7)' }] } },
      }],
    }],
  }
})
</script>

<style scoped>
.right {
  position: absolute;
  right: 0;
  top: 0;
  width: 620px;
  height: 1080px;
  padding: 108px 56px 0 0;
  display: flex;
  justify-content: flex-end;
  background: linear-gradient(270deg, rgba(5, 14, 28, 0.94) 0%, rgba(5, 14, 28, 0.82) 72%, rgba(5, 14, 28, 0) 100%);
  transition: transform 0.35s ease;
  pointer-events: none;
}
.right.collapsed { transform: translateX(550px); }
.inner { width: 464px; pointer-events: auto; display: flex; flex-direction: column; }
.cols { display: flex; gap: 30px; padding: 16px 4px 10px; }
.col { flex: 1; min-width: 0; }
.col-title { font-size: 15px; font-weight: 700; color: #fff; margin-bottom: 8px; letter-spacing: 1px; }
.item { padding: 9px 6px 10px; cursor: pointer; border-left: 2px solid transparent; }
.item:hover { background: rgba(47, 123, 255, 0.12); }
.item.sel { background: linear-gradient(90deg, rgba(79, 210, 255, 0.18), rgba(79, 210, 255, 0)); border-left-color: var(--cyan); }
.item.dim { opacity: 0.55; }
.line { display: flex; align-items: center; gap: 8px; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.dot.b { background: #a9c9ff; box-shadow: 0 0 6px #a9c9ff; }
.dot.g { background: var(--lime); box-shadow: 0 0 6px var(--lime); }
.name { font-size: 15px; color: var(--text-1); white-space: nowrap; }
.v { margin-left: auto; font-size: 19px; font-weight: 700; color: #fff; }
.track { position: relative; margin-top: 8px; height: 4px; background: rgba(143, 179, 217, 0.18); border-radius: 2px; }
.track i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 2px; transition: width 0.6s ease; }
.track i.b { background: linear-gradient(90deg, rgba(79, 210, 255, 0.2), #4fd2ff); }
.track i.g { background: linear-gradient(90deg, rgba(76, 255, 154, 0.2), #4cff9a); }
.track i::after {
  content: '';
  position: absolute;
  right: -4px;
  top: 50%;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  transform: translateY(-50%);
  background: #fff;
  box-shadow: 0 0 8px currentColor;
}
.track i.b::after { color: #4fd2ff; }
.track i.g::after { color: #4cff9a; }
.empty { height: 290px; display: grid; place-items: center; color: var(--text-3); }
.hint { color: var(--text-2); font-size: 12px; }
.radar { height: 360px; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 4px; }
.kpi {
  padding: 10px 4px;
  text-align: center;
  background: linear-gradient(180deg, rgba(47, 123, 255, 0.18), rgba(47, 123, 255, 0.04));
  border-top: 2px solid rgba(79, 210, 255, 0.7);
}
.kpi b { display: block; font-size: 24px; color: #fff; text-shadow: 0 0 8px rgba(79, 210, 255, 0.7); }
.kpi span { font-size: 12px; color: var(--text-2); }
.collapse {
  position: absolute;
  right: 532px;
  top: 108px;
  width: 26px;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  writing-mode: vertical-rl;
  color: var(--text-1);
  background: rgba(8, 26, 52, 0.85);
  border: 1px solid rgba(79, 190, 255, 0.4);
  cursor: pointer;
  pointer-events: auto;
}
.collapse svg { width: 8px; height: 12px; writing-mode: horizontal-tb; }
.collapse path { fill: none; stroke: var(--cyan); stroke-width: 2; }
</style>
