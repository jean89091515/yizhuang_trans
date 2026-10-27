<template>
  <div class="legend-wrap">
    <div class="compass" v-if="w" :title="`${w.name} ${w.speed} m/s（${w.level}级），烟羽去向 ${plumeDir}°`">
      <svg viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="34" fill="rgba(5,18,38,0.85)" stroke="rgba(79,210,255,0.5)" />
        <g fill="#8fb3d9" font-size="9" text-anchor="middle"><text x="40" y="14">N</text><text x="70" y="43">E</text><text x="40" y="73">S</text><text x="10" y="43">W</text></g>
        <g :style="{ transform: `rotate(${plumeDir}deg)`, transformOrigin: '40px 40px' }">
          <path d="M40 16 L47 44 L40 39 L33 44 Z" fill="#4fd2ff" />
          <path d="M40 39 L40 62" stroke="#4fd2ff" stroke-width="2" stroke-dasharray="3 3" />
        </g>
      </svg>
      <div class="ct"><b>{{ w.name }}</b><span class="num">{{ w.speed }} m/s · {{ w.level }}级</span><span>稳定度 {{ w.stability }}</span></div>
    </div>
    <div class="legend">
      <div v-for="it in items" :key="it.label" class="li"><i :style="it.style"></i>{{ it.label }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { state, result } from '../store.js'

const w = computed(() => result.value?.scenario?.wind)
const plumeDir = computed(() => Math.round(result.value?.plume?.plumeDirDeg ?? 45))
const sw = (c, extra = '') => ({ background: c, ...(extra ? { border: extra } : {}) })
const items = computed(() => {
  const v = state.view
  const hazard = [
    { label: 'ERPG-3 核心危险区', style: sw('rgba(255,77,79,0.45)', '1px solid #ff4d4f') },
    { label: 'ERPG-2 警戒区', style: sw('rgba(255,138,61,0.35)', '1px dashed #ff8a3d') },
    { label: 'ERPG-1 影响区', style: sw('rgba(255,210,63,0.25)', '1px dashed #ffd23f') },
    { label: '道路封闭区 / 拥堵区', style: sw('transparent', '2px dashed #ff4d4f') },
    { label: '亦庄控规界', style: sw('rgba(47,111,224,0.45)', '1px solid #4f9dff') },
  ]
  const supply = [
    { label: '消防站 / 应急仓库（供应点）', style: sw('#ff8a3d') },
    { label: '中转站（无人机起降）', style: { ...sw('#7b4dff'), borderRadius: '50%' } },
    { label: '货车路线（按物资类别着色）', style: { ...sw('linear-gradient(90deg,#ff4d4f,#ff8a3d,#ffd23f,#4fd2ff)'), height: '3px' } },
    { label: '无人机航线', style: { borderTop: '2px dashed #c77dff', height: '0' } },
    { label: '救援 / 医院 / 就地避难需求点', style: sw('#ffd23f') },
  ]
  const evac = [
    { label: '疏散起点（数字为剩余人数）', style: { ...sw('#ff8a3d'), borderRadius: '50%' } },
    { label: '救护车 / 直升机', style: { ...sw('linear-gradient(90deg,#ff5c7a 50%,#c77dff 50%)'), height: '3px' } },
    { label: '公交 / 私家车 / 地铁', style: { ...sw('linear-gradient(90deg,#3ddc97 33%,#a0b4c8 33% 66%,#2f7bff 66%)'), height: '3px' } },
    { label: '医院 / 避难所 / 地铁站', style: sw('linear-gradient(90deg,#fff 33%,#2fbf71 33% 66%,#2f7bff 66%)') },
  ]
  if (v === 'hazard') return hazard
  if (v === 'supply') return [...hazard.slice(0, 3), ...supply]
  if (v === 'evac') return [...hazard.slice(0, 3), ...evac]
  return [...hazard.slice(0, 3), supply[0], supply[2], supply[3], evac[0], evac[2]]
})
</script>

<style scoped>
.legend-wrap {
  position: absolute;
  left: 600px;
  bottom: 96px;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  pointer-events: auto;
}
.compass { display: flex; align-items: center; gap: 6px; padding: 4px 10px 4px 4px; background: rgba(5, 18, 38, 0.8); border: 1px solid rgba(79, 190, 255, 0.3); }
.compass svg { width: 72px; height: 72px; }
.compass svg g { transition: transform 0.6s ease; }
.ct { display: flex; flex-direction: column; gap: 2px; font-size: 12px; color: var(--text-2); }
.ct b { color: #fff; font-size: 14px; }
.legend {
  padding: 8px 12px;
  display: grid;
  grid-template-columns: auto;
  gap: 4px;
  background: rgba(5, 18, 38, 0.8);
  border: 1px solid rgba(79, 190, 255, 0.3);
  font-size: 12px;
  color: var(--text-1);
}
.li { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.li i { display: inline-block; width: 18px; height: 10px; flex: none; }
</style>
