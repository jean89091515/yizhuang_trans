import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// base: './' —— 构建产物可部署在任意子路径（如 /traffic-screen/emergency-sim/）或以 iframe 嵌入
export default defineConfig({
  base: './',
  plugins: [vue()],
  worker: { format: 'es' },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (/node_modules[\\/](echarts|zrender)[\\/]/.test(id)) return 'echarts'
          if (/node_modules[\\/]leaflet[\\/]/.test(id)) return 'leaflet'
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: { '/api': 'http://localhost:8787' },
  },
})
