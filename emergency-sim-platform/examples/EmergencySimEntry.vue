<template>
  <!--
    一体化平台（traffic-screen）“重大突发事件”入口的路由页面示例。
    将 emergency-sim-platform/dist 部署到 /traffic-screen/emergency-sim/（或任意路径）后，
    在路由表中注册本组件即可，例如：
      { path: '/emergency', name: 'Emergency', component: () => import('@/views/EmergencySimEntry.vue') }
    首页“重大突发事件”入口：router.push('/emergency')
    本模板同时兼容 Vue 2 / Vue 3（Options API）。
  -->
  <div class="emergency-sim-entry">
    <iframe ref="frame" :src="src" allow="fullscreen" frameborder="0"></iframe>
    <button class="back" @click="$router ? $router.back() : history.back()">返回首页</button>
  </div>
</template>

<script>
export default {
  name: 'EmergencySimEntry',
  props: {
    // 模拟模块部署地址（可改为配置项）
    src: { type: String, default: '/traffic-screen/emergency-sim/index.html' },
  },
  data() {
    return { lastResult: null }
  },
  mounted() {
    this._onMsg = (ev) => {
      const m = ev.data
      if (!m || typeof m.type !== 'string' || !m.type.startsWith('emergency-sim:')) return
      if (m.type === 'emergency-sim:back') { // 模块内“返回首页”按钮（config.js 中设置 homeUrl 时显示）
        this.$router ? this.$router.back() : history.back()
        return
      }
      if (m.type === 'emergency-sim:result') {
        this.lastResult = m.payload // 计算结果摘要，可写入平台其他模块
        this.$emit('result', m.payload)
      }
    }
    window.addEventListener('message', this._onMsg)
  },
  beforeDestroy() { window.removeEventListener('message', this._onMsg) }, // Vue 2
  beforeUnmount() { window.removeEventListener('message', this._onMsg) }, // Vue 3
  methods: {
    /** 供平台调用：如 this.$refs.sim.run({ windDir: 0, windSpeed: 3 }) */
    run(params) { this.post({ type: 'emergency-sim:run', params }) },
    setScenario(opts) { this.post({ type: 'emergency-sim:set', ...opts }) },
    post(msg) { this.$refs.frame && this.$refs.frame.contentWindow.postMessage(msg, '*') },
  },
}
</script>

<style scoped>
.emergency-sim-entry { position: fixed; inset: 0; background: #050d1a; }
.emergency-sim-entry iframe { width: 100%; height: 100%; display: block; }
.back {
  position: absolute; left: 24px; top: 20px; z-index: 2;
  padding: 4px 12px; color: #cfe6ff; background: rgba(8, 26, 52, 0.85);
  border: 1px solid rgba(79, 210, 255, 0.5); cursor: pointer;
}
</style>
