import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
        // AI 首次推理可能很慢，代理默认超时过短会向前端返回 502（易被误认为 Ollama 挂了）
        timeout: 600000,
        proxyTimeout: 600000,
        configure(proxy) {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setTimeout(600000)
          })
        },
      },
    },
  },
})
