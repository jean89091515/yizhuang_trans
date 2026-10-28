<template>
  <!-- 地图铺满视口（不参与缩放，保证 Leaflet 交互坐标准确） -->
  <MapView />
  <!-- 1920×1080 设计稿等比缩放层 -->
  <div class="screen" :style="screenStyle">
    <div class="vignette"></div>
    <ScreenFrame />
    <ScreenHeader @reset="reset" />
    <LeftPanel />
    <RightPanel />
    <ProcessOverlay />
    <MapLegend v-if="result" />
    <MapTools />
    <PlaybackBar />
    <div v-if="state.error && !state.running" class="toast">{{ state.error }}</div>
    <div v-if="!state.ready" class="loading">数据加载中…</div>
    <DetailModal />
    <AdvancedParams />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import MapView from './components/MapView.vue'
import ScreenFrame from './components/ScreenFrame.vue'
import ScreenHeader from './components/ScreenHeader.vue'
import LeftPanel from './components/LeftPanel.vue'
import RightPanel from './components/RightPanel.vue'
import ProcessOverlay from './components/ProcessOverlay.vue'
import MapLegend from './components/MapLegend.vue'
import MapTools from './components/MapTools.vue'
import PlaybackBar from './components/PlaybackBar.vue'
import DetailModal from './components/DetailModal.vue'
import AdvancedParams from './components/AdvancedParams.vue'
import { state, result, init, reset } from './store.js'

const vw = ref(window.innerWidth)
const vh = ref(window.innerHeight)
const onResize = () => { vw.value = window.innerWidth; vh.value = window.innerHeight }
const screenStyle = computed(() => {
  const s = Math.min(vw.value / 1920, vh.value / 1080)
  return { transform: `scale(${s})`, left: `${(vw.value - 1920 * s) / 2}px`, top: `${(vh.value - 1080 * s) / 2}px` }
})
onMounted(() => { window.addEventListener('resize', onResize); init().catch((e) => { state.error = `初始化失败：${e.message}` }) })
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
.screen {
  position: absolute;
  width: 1920px;
  height: 1080px;
  transform-origin: 0 0;
  pointer-events: none;
  z-index: 1000;
}
.vignette {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, rgba(5, 13, 26, 0.55) 0%, rgba(5, 13, 26, 0) 18%),
    linear-gradient(0deg, rgba(5, 13, 26, 0.6) 0%, rgba(5, 13, 26, 0) 16%);
}
.toast {
  position: absolute;
  left: 50%;
  bottom: 110px;
  transform: translateX(-50%);
  padding: 10px 18px;
  color: #fff;
  background: rgba(160, 20, 30, 0.85);
  border: 1px solid var(--red);
  pointer-events: auto;
}
.loading { position: absolute; inset: 0; display: grid; place-items: center; font-size: 20px; color: var(--cyan); }
</style>
