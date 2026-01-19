import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
    plugins: [react()],
    define: {
        'import.meta.env.VITE_SPA_CLIENT_ID': JSON.stringify(process.env.VITE_SPA_CLIENT_ID),
        'import.meta.env.VITE_API_CLIENT_ID': JSON.stringify(process.env.VITE_API_CLIENT_ID),
        'import.meta.env.VITE_AZURE_TENANT_ID': JSON.stringify(process.env.VITE_AZURE_TENANT_ID),
        'import.meta.env.VITE_API_URL': JSON.stringify(process.env.VITE_API_URL),
    },
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true
            }
        }
    }
})
