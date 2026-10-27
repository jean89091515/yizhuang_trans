<template>
  <!-- 屏幕外框：四角括号 + 边线 + 底部中央装饰 -->
  <svg class="frame" viewBox="0 0 1920 1080">
    <defs>
      <linearGradient id="fr-v" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#4fd2ff" stop-opacity="0" />
        <stop offset="0.5" stop-color="#4fd2ff" stop-opacity="0.45" />
        <stop offset="1" stop-color="#4fd2ff" stop-opacity="0" />
      </linearGradient>
      <linearGradient id="fr-bottom" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#4fd2ff" stop-opacity="0" />
        <stop offset="0.5" stop-color="#4fd2ff" stop-opacity="0.95" />
        <stop offset="1" stop-color="#4fd2ff" stop-opacity="0" />
      </linearGradient>
    </defs>
    <rect x="14" y="14" width="1892" height="1052" fill="none" stroke="#4fd2ff" stroke-opacity="0.12" />
    <path d="M14 200 V880" stroke="url(#fr-v)" stroke-width="2" />
    <path d="M1906 200 V880" stroke="url(#fr-v)" stroke-width="2" />
    <g fill="none" stroke="#4fd2ff" stroke-width="3">
      <path d="M14 60 V14 H60" /><path d="M1860 14 H1906 V60" />
      <path d="M14 1020 V1066 H60" /><path d="M1860 1066 H1906 V1020" />
    </g>
    <g fill="#19d3c5">
      <path d="M22 1052 l8 -8 v8z" /><path d="M1898 1052 l-8 -8 v8z" />
    </g>
    <!-- 底部中央装饰 -->
    <path d="M700 1066 H820 L840 1046 H1080 L1100 1066 H1220" fill="none" stroke="url(#fr-bottom)" stroke-width="2" />
    <path d="M860 1056 H1060" stroke="#9feaff" stroke-width="3" stroke-opacity="0.8" />
    <g fill="#4fd2ff"><circle cx="900" cy="1046" r="2.5" /><circle cx="1020" cy="1046" r="2.5" /></g>
  </svg>
</template>

<style scoped>
.frame { position: absolute; inset: 0; width: 1920px; height: 1080px; pointer-events: none; }
</style>
