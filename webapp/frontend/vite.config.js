import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 代理目标写字面 IPv4：Node 对 localhost 可能优先解析到 IPv6 [::1]，
// 而后端只监听 IPv4 时会 ECONNREFUSED，表现为前端所有 /api 请求 502。
// 需要改动后端端口时，用环境变量 SHOPVISION_API_TARGET 覆盖。
const API_TARGET = process.env.SHOPVISION_API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      ['/api', '/item-images', '/item-uploads', '/item-originals'].map((path) => [
        path,
        { target: API_TARGET, changeOrigin: true },
      ]),
    ),
  },
})