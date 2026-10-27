<template>
  <div ref="el" class="echart"></div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, markRaw } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, RadarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, RadarComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, RadarChart, GridComponent, TooltipComponent, LegendComponent, RadarComponent, CanvasRenderer])

const props = defineProps({ option: { type: Object, required: true } })
const emit = defineEmits(['click'])
const el = ref(null)
let chart = null
let ro = null

onMounted(() => {
  chart = markRaw(echarts.init(el.value, null, { renderer: 'canvas' }))
  chart.setOption(props.option)
  chart.on('click', (p) => emit('click', p))
  ro = new ResizeObserver(() => chart && chart.resize())
  ro.observe(el.value)
})
watch(() => props.option, (o) => chart && chart.setOption(o, true), { deep: false })
onBeforeUnmount(() => { ro?.disconnect(); chart?.dispose(); chart = null })
</script>

<style scoped>
.echart { width: 100%; height: 100%; }
</style>
