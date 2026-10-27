<template>
  <transition name="drop">
    <section v-if="state.processOpen" class="proc">
      <header>
        <span class="t">计算过程</span>
        <span class="st" :class="statusCls">{{ statusText }}</span>
        <span class="solver">{{ solverText }}</span>
        <button class="x" @click="state.processOpen = false" title="收起">×</button>
      </header>
      <div class="pipe">
        <div class="track"><i :style="{ width: progress * 100 + '%' }"></i></div>
        <div v-for="(s, i) in state.stages" :key="s.id" class="node" :class="s.status">
          <div class="dot">
            <svg v-if="s.status === 'done'" viewBox="0 0 16 16"><path d="M3 8.5l3.2 3L13 4.5" /></svg>
            <span v-else-if="s.status === 'skipped'">–</span>
            <span v-else>{{ i + 1 }}</span>
            <i v-if="s.status === 'running'" class="ring"></i>
          </div>
          <div class="nm" :title="s.name">{{ s.short || s.name }}</div>
          <div class="ms num">{{ s.status === 'done' ? (s.ms < 1 ? '<1' : Math.round(s.ms)) + ' ms' : s.status === 'running' ? '计算中' : s.status === 'skipped' ? '跳过' : '等待' }}</div>
        </div>
      </div>
      <div class="cur" v-if="current">
        <b>{{ current.name }}</b><span>{{ current.desc }}</span>
        <em v-if="current.summary">→ {{ current.summary }}</em>
      </div>
      <div class="console" ref="con">
        <div v-for="(l, i) in state.logs" :key="i" class="ln" :class="l.level">
          <span class="ts num">[{{ l.t.toFixed(3) }}s]</span> {{ l.msg }}
        </div>
        <div v-if="state.running" class="ln cursor">▍</div>
      </div>
    </section>
  </transition>
  <button v-if="!state.processOpen && result" class="pill" @click="state.processOpen = true">
    <i></i>计算完成 · 计算用时 {{ (result.computeMs / 1000).toFixed(2) }} s · 查看计算过程
  </button>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { state, result, progress } from '../store.js'

const con = ref(null)
watch(() => state.logs.length, async () => { await nextTick(); if (con.value) con.value.scrollTop = con.value.scrollHeight })

const current = computed(() => {
  const run = state.stages.find((s) => s.status === 'running')
  if (run) return run
  const done = [...state.stages].reverse().find((s) => s.status === 'done')
  return done || null
})
const statusText = computed(() => {
  if (state.error) return '计算失败'
  if (state.running) return `计算中 ${Math.round(progress.value * 100)}%`
  if (result.value) return `已完成 · 计算 ${(result.value.computeMs / 1000).toFixed(2)} s`
  return '待计算'
})
const statusCls = computed(() => (state.error ? 'err' : state.running ? 'run' : 'ok'))
const solverText = computed(() => (state.params.solver === 'remote' ? '服务端求解器' : '内置求解器 · Web Worker'))
</script>

<style scoped>
.proc {
  position: absolute;
  left: 600px;
  top: 140px;
  width: 720px;
  padding: 12px 16px 12px;
  background: rgba(5, 18, 38, 0.9);
  border: 1px solid rgba(79, 210, 255, 0.55);
  box-shadow: 0 0 24px rgba(47, 123, 255, 0.35), inset 0 0 18px rgba(47, 123, 255, 0.15);
  pointer-events: auto;
}
.proc::before, .proc::after {
  content: '';
  position: absolute;
  width: 14px;
  height: 14px;
  border: 2px solid var(--cyan);
}
.proc::before { left: -2px; top: -2px; border-right: none; border-bottom: none; }
.proc::after { right: -2px; bottom: -2px; border-left: none; border-top: none; }
header { display: flex; align-items: center; gap: 12px; }
.t { font-size: 17px; font-weight: 700; color: #fff; letter-spacing: 2px; }
.st { font-size: 13px; padding: 2px 8px; border-radius: 2px; }
.st.run { color: var(--cyan); background: rgba(79, 210, 255, 0.12); }
.st.ok { color: var(--lime); background: rgba(76, 255, 154, 0.12); }
.st.err { color: var(--red); background: rgba(255, 77, 79, 0.12); }
.solver { margin-left: auto; font-size: 12px; color: var(--text-2); }
.x { background: none; border: none; color: var(--text-2); font-size: 22px; cursor: pointer; line-height: 1; }
.x:hover { color: #fff; }

.pipe { position: relative; display: flex; justify-content: space-between; margin: 14px 6px 6px; }
.track { position: absolute; left: 34px; right: 34px; top: 15px; height: 2px; background: rgba(143, 179, 217, 0.25); }
.track i { position: absolute; left: 0; top: 0; bottom: 0; background: linear-gradient(90deg, var(--cyan), var(--lime)); box-shadow: 0 0 6px var(--cyan); transition: width 0.3s; }
.node { position: relative; width: 92px; display: flex; flex-direction: column; align-items: center; z-index: 1; }
.dot {
  position: relative;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-2);
  background: #0a1d3a;
  border: 2px solid rgba(143, 179, 217, 0.45);
}
.dot svg { width: 16px; height: 16px; }
.dot svg path { fill: none; stroke: #062; stroke-width: 2.4; }
.node.running .dot { color: #fff; border-color: var(--cyan); box-shadow: 0 0 12px var(--cyan); }
.node.done .dot { background: var(--lime); border-color: var(--lime); box-shadow: 0 0 10px rgba(76, 255, 154, 0.7); }
.node.skipped .dot { opacity: 0.5; }
.ring {
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 2px solid transparent;
  border-top-color: var(--cyan);
  border-right-color: var(--cyan);
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.nm { margin-top: 6px; font-size: 14px; color: var(--text-1); text-align: center; line-height: 1.2; height: 20px; white-space: nowrap; }
.node.running .nm { color: var(--cyan); font-weight: 700; }
.ms { font-size: 12px; color: var(--text-3); }
.node.done .ms { color: var(--lime); }
.cur { display: flex; gap: 8px; align-items: baseline; margin: 6px 4px 8px; font-size: 13px; color: var(--text-2); flex-wrap: wrap; }
.cur b { color: #fff; font-size: 14px; }
.cur em { font-style: normal; color: var(--yellow); }
.console {
  height: 136px;
  overflow-y: auto;
  padding: 8px 10px;
  background: rgba(0, 8, 20, 0.7);
  border: 1px solid rgba(79, 190, 255, 0.2);
  font-family: 'JetBrains Mono', 'Consolas', 'Menlo', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #9fc6ec;
  user-select: text;
}
.ln.warn { color: var(--yellow); }
.ln.error { color: var(--red); }
.ln.success { color: var(--lime); }
.ts { color: var(--text-3); margin-right: 4px; }
.cursor { animation: blink 1s steps(1) infinite; color: var(--cyan); }
@keyframes blink { 50% { opacity: 0; } }
.pill {
  position: absolute;
  left: 50%;
  top: 140px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  font-size: 13px;
  color: var(--text-1);
  background: rgba(5, 18, 38, 0.88);
  border: 1px solid rgba(79, 210, 255, 0.45);
  cursor: pointer;
  pointer-events: auto;
}
.pill i { width: 8px; height: 8px; border-radius: 50%; background: var(--lime); box-shadow: 0 0 6px var(--lime); }
.pill:hover { border-color: var(--cyan); color: #fff; }
.drop-enter-active, .drop-leave-active { transition: all 0.3s ease; }
.drop-enter-from, .drop-leave-to { opacity: 0; transform: translateY(-12px); }
</style>
