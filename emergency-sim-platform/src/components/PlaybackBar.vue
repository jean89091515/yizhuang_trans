<template>
  <div class="bottom">
    <SelectBox class="scheme" variant="scheme" drop-up v-model="state.supplyScheme" :options="schemeOptions" :disabled="!result?.supply" />
    <div class="pb" :class="{ off: !result }">
      <button class="play" @click="toggle" :disabled="!result" :title="state.playback.playing ? '暂停' : '播放'">
        <svg v-if="!state.playback.playing" viewBox="0 0 16 16"><path d="M4 2l10 6-10 6z" /></svg>
        <svg v-else viewBox="0 0 16 16"><path d="M3 2h4v12H3zM9 2h4v12H9z" /></svg>
      </button>
      <div class="tl">
        <input type="range" min="0" :max="tmax" step="0.5" v-model.number="state.playback.t" @input="state.playback.playing = false" :disabled="!result" />
        <div class="ticks"><span v-for="m in ticks" :key="m" :style="{ left: (m / tmax) * 100 + '%' }">{{ m }}</span></div>
      </div>
      <div class="clock num">T+{{ Math.floor(state.playback.t) }}<small>min</small></div>
      <button class="spd" @click="cycleSpeed" title="回放速度（仿真分钟/秒）">{{ state.playback.speed }}×</button>
      <div class="cnt" v-if="result">
        <span v-if="sup"><i class="s"></i>送达 <b class="num">{{ delivered }}</b>/{{ sup.totalTasks }}</span>
        <span v-if="ev"><i class="e"></i>疏散 <b class="num">{{ evacuated.toLocaleString() }}</b>/{{ ev.total.toLocaleString() }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, watch } from 'vue'
import SelectBox from './SelectBox.vue'
import { state, result } from '../store.js'
import { SUPPLY_SCHEMES } from '../engine/index.js'

const schemeOptions = SUPPLY_SCHEMES.map((s) => ({ value: s.key, label: s.label }))
const tmax = computed(() => result.value?.params?.evacuation?.Tmax ?? 180)
const ticks = computed(() => Array.from({ length: Math.floor(tmax.value / 30) + 1 }, (_, i) => i * 30))
const sup = computed(() => result.value?.supply?.schemes?.[state.supplyScheme])
const ev = computed(() => result.value?.evacuation?.schemes?.[state.evacScheme])
const delivered = computed(() => (sup.value ? sup.value.schedule.filter((p) => p.arrival <= state.playback.t).length : 0))
const evacuated = computed(() => (ev.value ? ev.value.schedule.reduce((s, x) => s + (x.arrival <= state.playback.t ? x.count : 0), 0) : 0))

let raf = 0
let last = 0
function loop(ts) {
  if (!state.playback.playing) return
  const dt = last ? (ts - last) / 1000 : 0
  last = ts
  state.playback.t = Math.min(tmax.value, state.playback.t + dt * state.playback.speed)
  if (state.playback.t >= tmax.value) { state.playback.playing = false; return }
  raf = requestAnimationFrame(loop)
}
watch(() => state.playback.playing, (p) => {
  cancelAnimationFrame(raf)
  if (p) { last = 0; raf = requestAnimationFrame(loop) }
}, { immediate: true })
onBeforeUnmount(() => cancelAnimationFrame(raf))

function toggle() {
  if (!state.playback.playing && state.playback.t >= tmax.value) state.playback.t = 0
  state.playback.playing = !state.playback.playing
}
const speeds = [2, 4, 8, 16]
function cycleSpeed() {
  state.playback.speed = speeds[(speeds.indexOf(state.playback.speed) + 1) % speeds.length]
}
</script>

<style scoped>
.bottom {
  position: absolute;
  left: 600px;
  width: 720px;
  bottom: 40px;
  display: flex;
  align-items: center;
  gap: 12px;
  pointer-events: auto;
}
.scheme { width: 236px; flex: none; }
.pb {
  flex: 1;
  height: 40px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  background: rgba(5, 18, 38, 0.86);
  border: 1px solid rgba(79, 190, 255, 0.45);
}
.pb.off { opacity: 0.5; }
.play {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid var(--cyan);
  background: rgba(47, 123, 255, 0.3);
  display: grid;
  place-items: center;
  cursor: pointer;
  padding: 0;
  flex: none;
}
.play svg { width: 12px; height: 12px; fill: #fff; }
.tl { position: relative; flex: 1; height: 28px; }
.tl input { width: 100%; margin: 0; height: 16px; accent-color: #4fd2ff; cursor: pointer; }
.ticks { position: relative; height: 12px; font-size: 10px; color: var(--text-3); }
.ticks span { position: absolute; transform: translateX(-50%); }
.clock { width: 74px; font-size: 18px; font-weight: 700; color: #fff; text-align: right; flex: none; }
.clock small { font-size: 11px; color: var(--text-2); margin-left: 2px; }
.spd { flex: none; font-size: 12px; color: var(--cyan); background: none; border: 1px solid rgba(79, 210, 255, 0.4); padding: 2px 6px; cursor: pointer; }
.cnt { display: flex; flex-direction: column; gap: 1px; font-size: 12px; color: var(--text-2); flex: none; min-width: 120px; }
.cnt b { color: #fff; font-size: 13px; }
.cnt i { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }
.cnt i.s { background: var(--yellow); }
.cnt i.e { background: var(--green); }
</style>
