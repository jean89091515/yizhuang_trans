<template>
  <div v-if="state.advancedOpen" class="mask" @click.self="close">
    <div class="modal">
      <header>
        <span class="t">高级参数</span>
        <span class="sub">与论文默认值一致；修改后点击“应用并计算”</span>
        <button class="x" @click="close">×</button>
      </header>
      <div class="body">
        <section v-for="g in groups" :key="g.title">
          <h4>{{ g.title }}</h4>
          <div class="grid">
            <label v-for="fd in g.fields" :key="fd.path" :title="fd.tip || ''">
              <span class="lb">{{ fd.label }}<em v-if="fd.unit">（{{ fd.unit }}）</em></span>
              <select v-if="fd.options" :value="get(fd.path)" @change="set(fd.path, fd.num ? +$event.target.value : $event.target.value)">
                <option v-for="o in fd.options" :key="o[0]" :value="o[0]">{{ o[1] }}</option>
              </select>
              <input v-else-if="fd.bool" type="checkbox" :checked="get(fd.path)" @change="set(fd.path, $event.target.checked)" />
              <input v-else type="number" :step="fd.step || 1" :min="fd.min" :max="fd.max" :placeholder="fd.placeholder || ''"
                :value="get(fd.path) ?? ''" @input="set(fd.path, $event.target.value === '' && fd.nullable ? null : +$event.target.value)" />
            </label>
          </div>
        </section>
      </div>
      <footer>
        <button class="btn ghost" @click="restore">恢复论文默认</button>
        <span class="sp"></span>
        <button class="btn ghost" @click="close">取消</button>
        <button class="btn" @click="apply">应用并计算</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { state, run } from '../store.js'
import { DEFAULT_PARAMS, WIND_PRESETS } from '../engine/defaults.js'

const draft = ref(null)
watch(() => state.advancedOpen, (o) => { if (o) draft.value = JSON.parse(JSON.stringify(state.params)) })

const get = (path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), draft.value)
function set(path, v) {
  const ks = path.split('.')
  let o = draft.value
  for (const k of ks.slice(0, -1)) o = o[k]
  o[ks[ks.length - 1]] = v
}

const stab = [['A', 'A 极不稳定'], ['B', 'B 不稳定'], ['C', 'C 弱不稳定'], ['D', 'D 中性（城市默认）'], ['E', 'E 弱稳定'], ['F', 'F 稳定']]
const groups = [
  { title: '泄漏源', fields: [
    { path: 'gas', label: '危化品', options: [['氯气', '氯气 Cl₂'], ['氨气', '氨气 NH₃']] },
    { path: 'leakRateKgMin', label: '泄漏速率', unit: 'kg/min', step: 0.5, min: 0.1 },
    { path: 'leakDurationMin', label: '泄漏持续时间', unit: 'min', min: 1 },
    { path: 'releaseHeightM', label: '有效释放高度', unit: 'm', step: 0.5, min: 0 },
  ] },
  { title: '气象', fields: [
    { path: 'windSpeed', label: '风速', unit: 'm/s', step: 0.1, min: 0.5 },
    { path: 'windDir', label: '风向（来向）', unit: '°，0=北风', min: 0, max: 359 },
    { path: 'stability', label: '大气稳定度', options: stab },
  ] },
  { title: 'ERPG 分区与人口', fields: [
    { path: 'zoneMode', label: '分区方式', options: [['buffered', '等值线外扩（论文）'], ['contour', '原始等值线'], ['auto', '论文级联策略']] },
    { path: 'zoneBuffersM.erpg3', label: 'ERPG-3 外扩', unit: 'm', step: 100 },
    { path: 'zoneBuffersM.erpg2', label: 'ERPG-2 外扩', unit: 'm', step: 100 },
    { path: 'zoneBuffersM.erpg1', label: 'ERPG-1 外扩', unit: 'm', step: 100 },
    { path: 'population.mode', label: '人口统计口径', options: [['intersect', '地块相交（论文）'], ['area', '面积加权']] },
    { path: 'population.k1Ratio', label: '重伤/中毒比例 k=1', step: 0.005, min: 0, max: 1 },
  ] },
  { title: '路网损伤', fields: [
    { path: 'roads.closureRadiusM', label: '道路封闭半径', unit: 'm', step: 100 },
    { path: 'roads.congestionRadiusM', label: 'BPR 拥堵半径', unit: 'm', step: 100 },
    { path: 'roads.vc', label: '流量容量比 v/c', step: 0.05 },
    { path: 'roads.circuity', label: '路网绕行系数', step: 0.05, tip: '无路网时的几何近似模型参数' },
    { path: 'roads.closureAccessKmh', label: '封闭区应急通行速度', unit: 'km/h', tip: '无路网时的几何近似模型参数' },
    { path: 'roads.vehicleSpeedCap', label: '路网车速上限（取车辆速度）', bool: true, tip: '有 road_network.json 时生效；取消勾选 = 与 network_router.py 一致，仅按道路自由流速度计时' },
    { path: 'roads.snapToMainComponent', label: '吸附到主连通路网', bool: true, tip: '有 road_network.json 时生效：点位只吸附到封闭后仍连通的主路网并计入接入段；不勾选 = 论文做法（最近节点）' },
  ] },
  { title: '人员疏散', fields: [
    { path: 'evacuation.Tmax', label: '疏散时长 T', unit: 'min', step: 5 },
    { path: 'evacuation.dt', label: '时间步长 Δt', unit: 'min', min: 1 },
    { path: 'evacuation.flexiblePriority', label: '弹性优先级', bool: true },
    { path: 'evacuation.k3ReservedRatio', label: 'k=3 预留运力比例', step: 0.05, min: 0, max: 1 },
    { path: 'evacuation.fleet.ambulance', label: '救护车', unit: '辆' },
    { path: 'evacuation.fleet.helicopter', label: '直升机', unit: '架' },
    { path: 'evacuation.fleet.bus', label: '公交车', unit: '辆' },
    { path: 'evacuation.fleet.car', label: '私家车', unit: '辆', nullable: true, placeholder: '自动（按通勤驾车比例）' },
    { path: 'evacuation.fleet.subway', label: '地铁', unit: '列' },
    { path: 'risk.dynamic', label: '风险随泄漏时长衰减', bool: true },
  ] },
  { title: '物资配送', fields: [
    { path: 'supply.trucks', label: '货车', unit: '辆' },
    { path: 'supply.drones', label: '无人机', unit: '架' },
    { path: 'supply.truckSpeedKmh', label: '货车速度', unit: 'km/h' },
    { path: 'supply.truckCapKg', label: '货车载重', unit: 'kg', step: 100 },
    { path: 'supply.droneSpeedKmh', label: '无人机速度', unit: 'km/h' },
    { path: 'supply.droneMaxKg', label: '无人机载重', unit: 'kg' },
    { path: 'supply.droneRangeM', label: '无人机航程', unit: 'm', step: 500 },
    { path: 'supply.maxIter', label: '2-opt 最大迭代', step: 10 },
  ] },
]

function close() { state.advancedOpen = false }
function restore() {
  const keep = { siteId: state.params.siteId, incident: state.params.incident, method: state.params.method, algorithm: state.params.algorithm, solver: state.params.solver }
  draft.value = { ...JSON.parse(JSON.stringify(DEFAULT_PARAMS)), ...keep }
}
function apply() {
  const d = draft.value
  const w = WIND_PRESETS.find((x) => x.speed === d.windSpeed && x.dir === d.windDir && x.stability === d.stability)
  d.windPresetId = w ? w.id : 'custom'
  state.params = d
  close()
  run()
}
</script>

<style scoped>
.mask { position: absolute; inset: 0; background: rgba(0, 6, 16, 0.55); display: grid; place-items: center; pointer-events: auto; z-index: 20; }
.modal { width: 1080px; max-height: 900px; display: flex; flex-direction: column; background: rgba(5, 18, 38, 0.97); border: 1px solid rgba(79, 210, 255, 0.6); box-shadow: 0 0 40px rgba(47, 123, 255, 0.4); }
header { display: flex; align-items: center; gap: 14px; padding: 12px 18px; border-bottom: 1px solid rgba(79, 190, 255, 0.3); background: linear-gradient(90deg, rgba(47, 123, 255, 0.3), transparent); }
.t { font-size: 19px; font-weight: 700; color: #fff; letter-spacing: 2px; }
.sub { font-size: 12px; color: var(--text-2); }
.x { margin-left: auto; background: none; border: none; color: var(--text-2); font-size: 26px; cursor: pointer; }
.body { overflow-y: auto; padding: 6px 18px 12px; }
h4 { margin: 14px 0 8px; font-size: 14px; color: var(--cyan); }
.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px 16px; }
label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-2); }
.lb em { font-style: normal; color: var(--text-3); }
input[type='number'], select {
  height: 30px;
  padding: 0 8px;
  color: #fff;
  font-size: 14px;
  background: rgba(10, 30, 60, 0.9);
  border: 1px solid rgba(79, 190, 255, 0.45);
  outline: none;
}
input[type='number']:focus, select:focus { border-color: var(--cyan); }
input[type='checkbox'] { width: 18px; height: 18px; accent-color: #4fd2ff; }
footer { display: flex; gap: 12px; padding: 12px 18px; border-top: 1px solid rgba(79, 190, 255, 0.25); }
.sp { flex: 1; }
.btn { padding: 7px 22px; font-size: 14px; color: #fff; cursor: pointer; background: linear-gradient(180deg, #2f7bff, #1b56c4); border: 1px solid var(--cyan); }
.btn.ghost { background: transparent; color: var(--text-1); border-color: rgba(79, 190, 255, 0.45); }
</style>
