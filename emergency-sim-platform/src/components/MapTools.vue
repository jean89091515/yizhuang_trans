<template>
  <div class="map-tools">
    <div v-if="state.mapScale.px" class="scale" title="比例尺">
      <span class="num">{{ state.mapScale.label }}</span>
      <i :style="{ width: state.mapScale.px + 'px' }"></i>
    </div>
    <button v-if="state.tileError && !state.layerPanelOpen" class="warn-pill" @click="state.layerPanelOpen = true">底图瓦片无法加载 ›</button>

    <div v-if="state.layerPanelOpen" class="panel">
      <div class="hd">底图</div>
      <div class="chips">
        <button v-for="b in basemaps" :key="b.id" :class="{ on: state.mapLayers.basemap === b.id }" @click="state.mapLayers.basemap = b.id">{{ b.name }}</button>
      </div>
      <div v-if="state.tileError" class="note warn">
        当前网络无法访问在线瓦片（无外网或被拦截）。可选“无底图”（道路、地铁矢量图层照常显示），或在 <code>config.js</code> 的 <code>map.basemaps</code> 中配置内网瓦片服务。
      </div>
      <div class="hd">图层</div>
      <label v-for="it in items" :key="it.key" class="row" :class="{ dis: it.disabled }">
        <input type="checkbox" v-model="state.mapLayers[it.key]" :disabled="it.disabled" />
        <i class="sw" :style="it.sw"></i>
        <span class="nm">{{ it.label }}</span>
        <span class="ex num">{{ it.extra }}</span>
      </label>
      <div v-if="!bm" class="note">
        未找到 <code>data/basemap.json</code>：道路、地铁图层由导出脚本从研究成果（Step2 路网、Step7 地铁）生成，见 README。
      </div>
    </div>

    <div class="btns">
      <button title="放大" @click="mapApi.zoomIn()"><svg viewBox="0 0 16 16"><path d="M8 3v10M3 8h10" /></svg></button>
      <button title="缩小" @click="mapApi.zoomOut()"><svg viewBox="0 0 16 16"><path d="M3 8h10" /></svg></button>
      <button title="复位到当前场景" @click="mapApi.fit()"><svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="4.5" /><path d="M8 1v3M8 12v3M1 8h3M12 8h3" /></svg></button>
      <button title="底图与图层" :class="{ on: state.layerPanelOpen }" @click="state.layerPanelOpen = !state.layerPanelOpen">
        <svg viewBox="0 0 16 16"><path d="M8 2l6 3.2L8 8.4 2 5.2z" /><path d="M2 8l6 3.2L14 8M2 10.8L8 14l6-3.2" /></svg>
        <em v-if="state.tileError" class="dot"></em>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { state, staticData } from '../store.js'
import { getBasemaps } from '../utils/basemap.js'
import { mapApi } from '../utils/mapApi.js'

const basemaps = getBasemaps()
const bm = computed(() => staticData.value?.basemap)
const items = computed(() => {
  const b = bm.value
  const nSubway = b ? new Set(b.subway.map((s) => s.name)).size : 0
  return [
    { key: 'roads', label: '路网', extra: b?.roads.length ? `${Math.round(b.totalKm).toLocaleString()} km` : '', disabled: !b?.roads.length, sw: { background: 'linear-gradient(90deg,#5ab0ff,#2d659f)', height: '3px' } },
    { key: 'roadStatus', label: '路网状态（封闭 / 拥堵）', extra: '', disabled: !b?.roads.length, sw: { background: 'linear-gradient(90deg,#ff3b4f 40%,#ff7a33 40% 70%,#ffe066 70%)', height: '3px' } },
    { key: 'roadLabels', label: '道路名称', extra: '', disabled: !b?.roads.some((r) => r.name), sw: { borderBottom: '1px dashed #8dbbe8', height: '6px' } },
    { key: 'subway', label: '地铁线路与站点', extra: nSubway ? `${nSubway} 条` : '', disabled: !b?.subway.length && !b?.stations.length, sw: { background: '#E91E63', height: '3px' } },
    { key: 'boundary', label: '亦庄控规界', extra: '', disabled: false, sw: { background: 'rgba(47,111,224,0.45)', border: '1px solid #4f9dff' } },
    { key: 'hazard', label: '灾害范围（分区 / 浓度）', extra: '', disabled: false, sw: { background: 'rgba(255,138,61,0.35)', border: '1px dashed #ff8a3d' } },
  ]
})
</script>

<style scoped>
.map-tools {
  position: absolute;
  right: 612px;
  bottom: 96px;
  display: flex;
  align-items: flex-end;
  gap: 8px;
  pointer-events: none;
}
.map-tools > * { pointer-events: auto; }
.btns { display: flex; flex-direction: column; gap: 6px; }
.btns button {
  position: relative;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  padding: 0;
  cursor: pointer;
  background: rgba(5, 18, 38, 0.86);
  border: 1px solid rgba(79, 190, 255, 0.45);
}
.btns button:hover, .btns button.on { border-color: var(--cyan); background: rgba(47, 123, 255, 0.35); }
.btns svg { width: 16px; height: 16px; fill: none; stroke: #cfe6ff; stroke-width: 1.6; stroke-linejoin: round; }
.dot { position: absolute; right: 3px; top: 3px; width: 7px; height: 7px; border-radius: 50%; background: var(--red); box-shadow: 0 0 6px var(--red); }
.scale { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; font-size: 11px; color: var(--text-1); text-shadow: 0 0 3px #000; pointer-events: none; }
.scale i { display: block; height: 5px; border: 1.5px solid #cfe6ff; border-top: none; }
.warn-pill {
  padding: 5px 10px;
  font-size: 12px;
  color: #ffd9d9;
  cursor: pointer;
  background: rgba(120, 20, 30, 0.75);
  border: 1px solid rgba(255, 77, 79, 0.7);
}
.panel {
  width: 268px;
  padding: 10px 12px 12px;
  background: rgba(5, 18, 38, 0.94);
  border: 1px solid rgba(79, 210, 255, 0.55);
  box-shadow: 0 0 18px rgba(47, 123, 255, 0.3);
  font-size: 13px;
  color: var(--text-1);
}
.hd { margin: 2px 0 6px; font-size: 13px; font-weight: 700; color: #fff; letter-spacing: 1px; border-left: 3px solid var(--cyan); padding-left: 6px; }
.hd + .chips, .chips + .note, .chips + .hd { margin-bottom: 10px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chips button {
  padding: 3px 9px;
  font-size: 12px;
  color: var(--text-1);
  cursor: pointer;
  background: rgba(14, 36, 66, 0.8);
  border: 1px solid rgba(79, 190, 255, 0.35);
}
.chips button.on { color: #fff; background: rgba(47, 123, 255, 0.5); border-color: var(--cyan); }
.row { display: flex; align-items: center; gap: 7px; padding: 3px 0; cursor: pointer; }
.row.dis { opacity: 0.4; cursor: default; }
.row input { width: 15px; height: 15px; margin: 0; accent-color: #4fd2ff; }
.sw { display: inline-block; width: 18px; height: 10px; flex: none; }
.nm { flex: 1; white-space: nowrap; }
.ex { font-size: 12px; color: var(--text-2); }
.note { margin: 6px 0 4px; font-size: 12px; line-height: 1.5; color: var(--text-2); }
.note.warn { color: #ffc9c9; }
.note code { color: var(--cyan); }
</style>
