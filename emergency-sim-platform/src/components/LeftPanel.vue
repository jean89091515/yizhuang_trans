<template>
  <aside class="left" :class="{ collapsed: state.leftCollapsed }">
    <div class="inner">
      <!-- 计算设置 -->
      <div class="panel-title">计算设置</div>
      <div class="rows">
        <div class="row" v-for="r in rows" :key="r.key">
          <div class="chip">
            <svg viewBox="0 0 20 22" class="shield"><path d="M10 1 L18 4 V11 C18 16 14 19.5 10 21 C6 19.5 2 16 2 11 V4 Z" fill="url(#shield-g)" stroke="#9feaff" stroke-width="1" /><path d="M6 11 l3 3 5-6" fill="none" stroke="#fff" stroke-width="1.8" /></svg>
            <span>{{ r.label }}</span>
          </div>
          <SelectBox class="val" v-model="state.params[r.key]" :options="r.options" :disabled="state.running" />
        </div>
      </div>
      <svg width="0" height="0" style="position:absolute"><defs><linearGradient id="shield-g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3d8bff" /><stop offset="1" stop-color="#123c8a" /></linearGradient></defs></svg>

      <!-- 参数调整 -->
      <div class="panel-title">参数调整
        <div class="extra"><button class="link-btn" @click="state.advancedOpen = true">⚙ 高级参数</button></div>
      </div>
      <div class="params">
        <div class="pcol">
          <div class="plabel">事故发生地</div>
          <PlatformIcon :active="state.pickMode || state.running" />
          <SelectBox variant="compact" :model-value="siteValue" :options="siteOptions" :disabled="state.running" @change="setSite" />
        </div>
        <div class="pcol">
          <div class="plabel">风况</div>
          <PlatformIcon :active="state.running" />
          <SelectBox variant="compact" :model-value="state.params.windPresetId" :options="windOptions" :disabled="state.running" @change="setWind" />
        </div>
      </div>
      <div class="pinfo">
        <span>{{ state.params.gas }} {{ state.params.leakRateKgMin }} kg/min</span>
        <i>|</i>
        <span>{{ windName }} {{ state.params.windSpeed }} m/s（{{ level }}级）</span>
        <i>|</i>
        <span>稳定度 {{ state.params.stability }}</span>
      </div>
      <div v-if="state.pickMode" class="pick-hint">请在地图上点击选择事故发生地</div>

      <!-- 开始计算 -->
      <div class="start-wrap">
        <span class="arr l"></span>
        <button class="start" :class="{ running: state.running }" :disabled="state.running" @click="run">
          <span v-if="!state.running">开始计算</span>
          <span v-else>计算中… {{ Math.round(progress * 100) }}%</span>
          <i class="bar" :style="{ width: (state.running ? progress * 100 : 0) + '%' }"></i>
        </button>
        <span class="arr r"></span>
      </div>

      <!-- 算法能力 -->
      <div class="panel-title">算法能力
        <div class="extra tab-group">
          <button :class="{ active: abilityTab === 'amb' }" @click="abilityTab = 'amb'">救护车规模</button>
          <button :class="{ active: abilityTab === 'drone' }" @click="abilityTab = 'drone'">无人机规模</button>
        </div>
      </div>
      <div class="chart">
        <EChart v-if="abilityOption" :option="abilityOption" />
        <div v-else class="empty">{{ state.running ? '计算中…' : '暂无数据' }}</div>
      </div>
    </div>
    <button class="collapse" @click="state.leftCollapsed = !state.leftCollapsed">
      <span>{{ state.leftCollapsed ? '展开' : '收起' }}</span>
      <svg viewBox="0 0 8 12"><path :d="state.leftCollapsed ? 'M2 1l5 5-5 5' : 'M6 1L1 6l5 5'" /></svg>
    </button>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue'
import SelectBox from './SelectBox.vue'
import PlatformIcon from './PlatformIcon.vue'
import EChart from './EChart.vue'
import {
  state, result, progress, run, setSite, setWind,
  SITE_OPTIONS, WIND_OPTIONS, METHOD_OPTIONS, ALGORITHM_OPTIONS, SOLVER_OPTIONS,
} from '../store.js'
import { beaufort, windDirName } from '../engine/defaults.js'

const rows = [
  { key: 'method', label: '方法', options: METHOD_OPTIONS },
  { key: 'algorithm', label: '算法', options: ALGORITHM_OPTIONS },
  { key: 'solver', label: '求解器', options: SOLVER_OPTIONS },
]
const siteValue = computed(() => (state.pickMode ? 'custom' : state.params.siteId))
const siteOptions = computed(() => SITE_OPTIONS.map((o) => (o.value === 'custom' && state.params.siteId === 'custom' && !state.pickMode
  ? { ...o, label: '自定义点', desc: `${state.params.incident.lon.toFixed(4)}°E, ${state.params.incident.lat.toFixed(4)}°N（再次选择可重新点选）` }
  : o)))
const level = computed(() => beaufort(state.params.windSpeed))
const windName = computed(() => windDirName(state.params.windDir))
const abilityTab = ref('amb')
const windOptions = computed(() => state.params.windPresetId === 'custom'
  ? [...WIND_OPTIONS, { value: 'custom', label: '自定义风况', desc: `${state.params.windSpeed} m/s · ${state.params.windDir}°` }]
  : WIND_OPTIONS)

const axisStyle = {
  axisLine: { lineStyle: { color: 'rgba(143,179,217,0.4)' } },
  axisLabel: { color: '#8fb3d9', fontSize: 12 },
  splitLine: { lineStyle: { color: 'rgba(143,179,217,0.12)', type: 'dashed' } },
  nameTextStyle: { color: '#8fb3d9', fontSize: 12 },
}

const abilityOption = computed(() => {
  const r = result.value
  if (!r) return null
  let x, s1, s2, n1, n2, u1, u2, xName
  if (abilityTab.value === 'amb') {
    const s = r.evacuation?.sensitivityAmbulance
    if (!s) return null
    x = s.map((d) => d.n)
    s1 = s.map((d) => +(d.rate * 100).toFixed(1))
    s2 = s.map((d) => +(d.risk / 1e4).toFixed(1))
    n1 = '疏散完成率'; n2 = '累计风险'; u1 = '%'; u2 = '万'; xName = '救护车(辆)'
  } else {
    const s = r.supply?.sensitivityDrones
    if (!s) return null
    x = s.map((d) => d.n)
    s1 = s.map((d) => +(d.completionRate * 100).toFixed(1))
    s2 = s.map((d) => +d.makespan.toFixed(1))
    n1 = '配送完成率'; n2 = 'Makespan'; u1 = '%'; u2 = 'min'; xName = '无人机(架)'
  }
  return {
    grid: { left: 46, right: 50, top: 40, bottom: 46 },
    legend: { top: 4, right: 8, itemWidth: 10, itemHeight: 6, textStyle: { color: '#cfe6ff', fontSize: 12 }, icon: 'rect' },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(6,22,44,0.92)', borderColor: '#4fd2ff', textStyle: { color: '#fff' } },
    xAxis: { type: 'category', data: x, ...axisStyle, name: xName, nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: '#8fb3d9', fontSize: 12 }, splitLine: { show: false } },
    yAxis: [
      { type: 'value', name: u1, ...axisStyle, scale: true },
      { type: 'value', name: u2, ...axisStyle, splitLine: { show: false }, scale: true },
    ],
    series: [
      { name: n1, type: 'line', data: s1, smooth: false, symbol: 'circle', symbolSize: 6, lineStyle: { color: '#a9c9ff', width: 2 }, itemStyle: { color: '#a9c9ff' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(169,201,255,0.25)' }, { offset: 1, color: 'rgba(169,201,255,0)' }] } } },
      { name: n2, type: 'line', yAxisIndex: 1, data: s2, smooth: false, symbol: 'circle', symbolSize: 6, lineStyle: { color: '#4cff9a', width: 2 }, itemStyle: { color: '#4cff9a' } },
    ],
  }
})
</script>

<style scoped>
.left {
  position: absolute;
  left: 0;
  top: 0;
  width: 600px;
  height: 1080px;
  padding: 108px 0 0 58px;
  background: linear-gradient(90deg, rgba(5, 14, 28, 0.94) 0%, rgba(5, 14, 28, 0.82) 72%, rgba(5, 14, 28, 0) 100%);
  transition: transform 0.35s ease;
  pointer-events: none;
}
.left.collapsed { transform: translateX(-530px); }
.inner { width: 456px; pointer-events: auto; display: flex; flex-direction: column; }
.rows { display: flex; flex-direction: column; gap: 14px; padding: 18px 0 22px 4px; }
.row { display: flex; gap: 16px; align-items: center; }
.chip {
  width: 122px;
  height: 42px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  font-size: 17px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 3px;
  background: linear-gradient(180deg, rgba(30, 80, 160, 0.85), rgba(12, 40, 90, 0.85));
  border: 1px solid rgba(79, 190, 255, 0.7);
  border-radius: 4px;
  box-shadow: inset 0 0 10px rgba(79, 210, 255, 0.35);
}
.shield { width: 22px; height: 24px; flex: none; filter: drop-shadow(0 0 4px rgba(79, 210, 255, 0.8)); }
.val { flex: 1; }

.params { display: flex; justify-content: space-around; padding: 14px 6px 0; }
.pcol { display: flex; flex-direction: column; align-items: center; width: 190px; position: relative; }
.plabel {
  position: absolute;
  top: 10px;
  z-index: 2;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 2px;
  text-shadow: 0 0 6px #000, 0 0 10px rgba(79, 210, 255, 0.8);
}
.pcol .sel { width: 170px; margin-top: 2px; }
.pinfo {
  margin: 12px 4px 0;
  font-size: 13px;
  color: var(--text-2);
  display: flex;
  justify-content: center;
  gap: 8px;
}
.pinfo i { color: var(--text-3); font-style: normal; }
.pick-hint {
  margin: 8px 4px 0;
  padding: 6px 10px;
  text-align: center;
  font-size: 13px;
  color: var(--yellow);
  border: 1px dashed rgba(255, 210, 63, 0.6);
  animation: blink 1.2s ease-in-out infinite;
}
@keyframes blink { 50% { opacity: 0.5; } }

.start-wrap { display: flex; align-items: center; gap: 10px; margin: 18px 0 22px; }
.arr { width: 0; height: 0; border-top: 7px solid transparent; border-bottom: 7px solid transparent; filter: drop-shadow(0 0 4px var(--lime)); }
.arr.l { border-left: 10px solid var(--lime); }
.arr.r { border-right: 10px solid var(--lime); }
.start {
  position: relative;
  flex: 1;
  height: 46px;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 6px;
  color: #fff;
  cursor: pointer;
  background: linear-gradient(180deg, rgba(20, 60, 120, 0.9), rgba(8, 28, 60, 0.9));
  border: 1px solid rgba(79, 210, 255, 0.85);
  box-shadow: inset 0 0 14px rgba(79, 210, 255, 0.35), 0 0 10px rgba(79, 210, 255, 0.25);
  overflow: hidden;
}
.start:hover:not(:disabled) { box-shadow: inset 0 0 18px rgba(79, 210, 255, 0.6), 0 0 16px rgba(79, 210, 255, 0.5); }
.start:disabled { cursor: progress; letter-spacing: 2px; }
.start .bar {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--cyan), var(--lime));
  box-shadow: 0 0 8px var(--lime);
  transition: width 0.3s;
}
.start.running::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(79, 210, 255, 0.25), transparent);
  animation: shimmer 1.2s linear infinite;
}
@keyframes shimmer { from { transform: translateX(-100%); } to { transform: translateX(100%); } }

.chart { height: 300px; margin-top: 6px; }
.empty { height: 100%; display: grid; place-items: center; color: var(--text-3); }

.collapse {
  position: absolute;
  left: 528px;
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
