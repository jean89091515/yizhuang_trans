<template>
  <!-- 等轴测发光平台图标（参数调整区） -->
  <svg class="pf" viewBox="0 0 160 120" :class="{ active }">
    <defs>
      <linearGradient :id="`beam-${uid}`" x1="0" y1="1" x2="0" y2="0">
        <stop offset="0" stop-color="#4fd2ff" stop-opacity="0.85" />
        <stop offset="1" stop-color="#4fd2ff" stop-opacity="0" />
      </linearGradient>
      <linearGradient :id="`top-${uid}`" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#2a6fd6" />
        <stop offset="1" stop-color="#0f2f66" />
      </linearGradient>
      <linearGradient :id="`side-${uid}`" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#1b4f9e" />
        <stop offset="1" stop-color="#081a3a" />
      </linearGradient>
      <filter :id="`glow-${uid}`"><feGaussianBlur stdDeviation="2.4" /></filter>
    </defs>
    <!-- 光柱 -->
    <polygon :fill="`url(#beam-${uid})`" points="52,20 108,20 120,70 40,70" opacity="0.55" class="beam" />
    <ellipse cx="80" cy="66" rx="34" ry="11" fill="#4fd2ff" opacity="0.35" :filter="`url(#glow-${uid})`" />
    <!-- 平台侧面 -->
    <polygon :fill="`url(#side-${uid})`" points="20,74 80,104 80,114 20,84" />
    <polygon :fill="`url(#side-${uid})`" points="140,74 80,104 80,114 140,84" opacity="0.8" />
    <!-- 平台顶面 -->
    <polygon :fill="`url(#top-${uid})`" stroke="#4fd2ff" stroke-width="1.2" points="80,44 140,74 80,104 20,74" />
    <!-- 网格 -->
    <g stroke="#4fd2ff" stroke-opacity="0.35" stroke-width="0.8">
      <line x1="50" y1="59" x2="110" y2="89" />
      <line x1="110" y1="59" x2="50" y2="89" />
      <line x1="65" y1="51.5" x2="125" y2="81.5" />
      <line x1="35" y1="66.5" x2="95" y2="96.5" />
      <line x1="95" y1="51.5" x2="35" y2="81.5" />
      <line x1="125" y1="66.5" x2="65" y2="96.5" />
    </g>
    <!-- 中心立方体 -->
    <g class="cube">
      <polygon fill="#7fe3ff" opacity="0.9" points="80,56 96,64 80,72 64,64" />
      <polygon fill="#2f7bff" opacity="0.9" points="64,64 80,72 80,82 64,74" />
      <polygon fill="#1b56c4" opacity="0.9" points="96,64 80,72 80,82 96,74" />
    </g>
    <!-- 边缘高光 -->
    <polyline fill="none" stroke="#9feaff" stroke-width="1.6" points="20,74 80,104 140,74" :filter="`url(#glow-${uid})`" opacity="0.8" />
  </svg>
</template>

<script setup>
defineProps({ active: Boolean })
const uid = Math.random().toString(36).slice(2, 8)
</script>

<style scoped>
.pf { width: 150px; height: 112px; display: block; }
.beam { animation: beam 2.6s ease-in-out infinite; transform-origin: 80px 70px; }
.cube { animation: float 2.6s ease-in-out infinite; }
.active .beam { animation-duration: 0.9s; }
@keyframes beam { 0%, 100% { opacity: 0.35; } 50% { opacity: 0.75; } }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
</style>
