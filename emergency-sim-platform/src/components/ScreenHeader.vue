<template>
  <header class="hdr">
    <svg class="deco" viewBox="0 0 1920 120" preserveAspectRatio="none">
      <defs>
        <linearGradient id="hdr-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#06142a" stop-opacity="0.96" />
          <stop offset="1" stop-color="#06142a" stop-opacity="0" />
        </linearGradient>
        <linearGradient id="hdr-plate" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#0b2a5c" stop-opacity="0.95" />
          <stop offset="1" stop-color="#0a3f86" stop-opacity="0.55" />
        </linearGradient>
        <linearGradient id="hdr-line" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#4fd2ff" stop-opacity="0.1" />
          <stop offset="0.3" stop-color="#4fd2ff" stop-opacity="0.9" />
          <stop offset="0.5" stop-color="#bff0ff" stop-opacity="1" />
          <stop offset="0.7" stop-color="#4fd2ff" stop-opacity="0.9" />
          <stop offset="1" stop-color="#4fd2ff" stop-opacity="0.1" />
        </linearGradient>
        <filter id="hdr-glow" x="-20%" y="-200%" width="140%" height="500%"><feGaussianBlur stdDeviation="3" /></filter>
      </defs>
      <rect x="0" y="0" width="1920" height="120" fill="url(#hdr-bg)" />
      <!-- 中央标题牌 -->
      <path d="M560 0 H1360 L1318 64 H602 Z" fill="url(#hdr-plate)" />
      <path d="M560 0 L602 64 H1318 L1360 0" fill="none" stroke="#4fd2ff" stroke-width="2" opacity="0.9" />
      <!-- 两侧折线 -->
      <path d="M22 40 H500 L530 52 H560 M1360 52 H1390 L1420 40 H1898" fill="none" stroke="url(#hdr-line)" stroke-width="2" />
      <path d="M22 46 H496" stroke="#4fd2ff" stroke-opacity="0.25" stroke-width="1" />
      <path d="M1424 46 H1898" stroke="#4fd2ff" stroke-opacity="0.25" stroke-width="1" />
      <!-- 发光底线 -->
      <path d="M760 64 H1160" stroke="#9feaff" stroke-width="4" filter="url(#hdr-glow)" />
      <path d="M800 64 H1120" stroke="#e8fbff" stroke-width="2" />
      <!-- 点阵装饰 -->
      <g fill="#4fd2ff">
        <circle cx="420" cy="28" r="3" /><circle cx="434" cy="28" r="3" opacity="0.6" /><circle cx="448" cy="28" r="3" opacity="0.3" />
        <circle cx="1472" cy="28" r="3" opacity="0.3" /><circle cx="1486" cy="28" r="3" opacity="0.6" /><circle cx="1500" cy="28" r="3" />
      </g>
      <g fill="#19d3c5">
        <rect x="300" y="24" width="40" height="6" rx="3" opacity="0.8" /><rect x="1580" y="24" width="40" height="6" rx="3" opacity="0.8" />
      </g>
    </svg>
    <h1 class="title">{{ title }}</h1>
    <div class="subtitle">
      <svg viewBox="0 0 20 20" class="ico"><path d="M2 8 L10 3 L18 8 Z M4 9 h12 v1 H4z M5 11 h2 v5 H5z M9 11 h2 v5 H9z M13 11 h2 v5 h-2z M3 17 h14 v1.5 H3z" fill="currentColor" /></svg>
      <span>{{ subtitle }}</span>
    </div>
    <div class="tools">
      <button class="icon-btn" title="重置为论文基准场景并重新计算" @click="$emit('reset')">
        <svg viewBox="0 0 24 24"><path d="M12 5a7 7 0 1 1-6.6 4.7" fill="none" stroke="currentColor" stroke-width="2" /><path d="M4 4v6h6" fill="none" stroke="currentColor" stroke-width="2" /></svg>
      </button>
      <SelectBox v-model="state.view" :options="VIEW_OPTIONS" variant="compact" class="view-sel" />
    </div>
  </header>
</template>

<script setup>
import SelectBox from './SelectBox.vue'
import { state, VIEW_OPTIONS } from '../store.js'

defineEmits(['reset'])
const cfg = window.EMERGENCY_SIM_CONFIG || {}
const title = cfg.title || '宏中微一体化交通计算示范平台'
const subtitle = cfg.subtitle || '北京亦庄 重大突发事件下交通流传播运行'
</script>

<style scoped>
.hdr { position: absolute; left: 0; top: 0; width: 1920px; height: 140px; pointer-events: none; z-index: 5; }
.deco { position: absolute; inset: 0; width: 1920px; height: 120px; }
.title {
  position: absolute;
  left: 0;
  right: 0;
  top: 6px;
  margin: 0;
  text-align: center;
  font-family: var(--font-title);
  font-size: 40px;
  font-style: italic;
  font-weight: 900;
  letter-spacing: 6px;
  background: linear-gradient(180deg, #ffffff 30%, #9fdcff 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  filter: drop-shadow(0 0 8px rgba(79, 210, 255, 0.55));
}
.subtitle {
  position: absolute;
  left: 50%;
  top: 88px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 18px 0 10px;
  font-size: 17px;
  font-weight: 600;
  color: #eaf6ff;
  background: linear-gradient(180deg, rgba(14, 50, 100, 0.92), rgba(8, 30, 62, 0.92));
  border: 1px solid rgba(79, 210, 255, 0.75);
  box-shadow: 0 0 12px rgba(79, 210, 255, 0.35), inset 0 0 10px rgba(47, 123, 255, 0.3);
  white-space: nowrap;
}
.subtitle .ico {
  width: 26px;
  height: 26px;
  padding: 3px;
  color: #fff;
  background: linear-gradient(180deg, #3d8bff, #1b56c4);
  border-radius: 3px;
}
.tools {
  position: absolute;
  right: 72px;
  top: 64px;
  display: flex;
  align-items: center;
  gap: 14px;
  pointer-events: auto;
}
.icon-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 1px solid rgba(79, 210, 255, 0.6);
  background: rgba(8, 26, 52, 0.85);
  color: var(--text-0);
  cursor: pointer;
  display: grid;
  place-items: center;
  padding: 0;
}
.icon-btn svg { width: 18px; height: 18px; }
.icon-btn:hover { box-shadow: 0 0 10px var(--cyan); color: var(--cyan); }
.view-sel { width: 140px; }
</style>
