import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // 开发环境把 /api 代理到后端，避免跨域配置
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
    // 提前预热入口文件，避免首次打开页面时才开始编译导致卡顿
    warmup: {
      clientFiles: ['./src/main.ts', './src/router/index.ts', './src/views/dashboard/index.vue'],
    },
  },
  // 显式预构建重依赖：冷启动一次性完成，页面首开不再触发大量转译
  optimizeDeps: {
    include: ['element-plus', 'vue', 'vue-router', 'pinia', 'axios', 'dayjs'],
  },
})
