/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { VitePWA } from 'vite-plugin-pwa'

// As hrms/frontend/vite.config.js. `frontendRoute` is where the site serves the app: the plugin
// proxies the bench in development and builds into card/public/frontend and card/www/cdms.html.
export default defineConfig({
  plugins: [
    frappeui({
      frontendRoute: '/cdms',
      // explicit, so the build also works outside a bench (CI)
      buildConfig: {
        outDir: '../card/public/frontend',
        indexHtmlPath: '../card/www/cdms.html',
        baseUrl: '/assets/card/frontend/',
      },
    }),
    vue(),
    // injectManifest with public/sw.js; main.ts registers it at /cdms/sw.js (card/pwa.py).
    VitePWA({
      registerType: 'autoUpdate',
      strategies: 'injectManifest',
      injectRegister: null,
      injectManifest: { globPatterns: ['**/*.{js,css,woff2,png}'] },
      manifest: {
        name: 'CARD Mobile',
        short_name: 'CARD',
        id: '/cdms/',
        start_url: '/cdms/',
        scope: '/cdms/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#ffffff',
        theme_color: '#1F876C',
        icons: [
          { src: '/assets/card/frontend/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/assets/card/frontend/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/assets/card/frontend/icons/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
    }),
  ],
  test: { environment: 'node', include: ['src/**/*.spec.ts'] },
})
