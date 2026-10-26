import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import vueDevTools from 'vite-plugin-vue-devtools'

export default defineConfig({
    plugins: [
        vueDevTools({
            launchEditor: 'webstorm',
        }),
        vue({
            template: {
                compilerOptions: {
                    isCustomElement: tag => tag === 'pwa-install'
                }
            }
        }),
        tailwindcss(),
        VueI18nPlugin({
            /* options */
            // locale messages resource pre-compile option
            include: [path.resolve(__dirname, './src/locales/**')]
        }),
        VitePWA({
            registerType: 'autoUpdate',
            manifest: {
                id: 'period_tracker',
                name: 'Period Tracker',
                short_name: 'Period Tracker',
                description: 'Track your menstrual cycle',
                start_url: "/",
                theme_color: '#FAF6F2', // warm paper (light theme background)
                background_color: '#FAF6F2',
                display: 'standalone',
                launch_handler: {
                    "client_mode": "auto"
                },
                orientation: 'any',
                categories: ['health'],
                dir: 'ltr',
                shortcuts: [
                    {
                        "name": "Dashboard",
                        "url": "/dashboard",
                        "description": "Show my dashboard.",
                        "icons": [
                            {
                                "src": "assets/icons/home.png",
                                "type": "image/png",
                                "purpose": "maskable"
                            }
                        ]
                    },
                    {
                        "name": "Account",
                        "url": "/account",
                        "description": "Manage you account.",
                        "icons": [
                            {
                                "src": "assets/icons/userCircle.png",
                                "type": "image/png",
                                "purpose": "maskable"
                            }
                        ]
                    }
                ],
                icons: [
                    {
                        src: "assets/icons/ios/512.png",
                        type: "image/png",
                        purpose: "any",
                        sizes: "512x512"
                    },
                    {
                        src: "assets/icons/ios/192.png",
                        type: "image/png",
                        purpose: "any",
                        sizes: "192x192"
                    },
                    {
                        src: "assets/icons/ios/180.png",
                        type: "image/png",
                        purpose: "any",
                        sizes: "180x180"
                    },
                    {
                        src: "assets/icons/android/android-launchericon-512-512.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "512x512"
                    },
                    {
                        src: "assets/icons/android/android-launchericon-192-192.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "192x192"
                    },
                    {
                        src: "assets/icons/android/android-launchericon-144-144.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "144x144"
                    },
                    {
                        src: "assets/icons/android/android-launchericon-96-96.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "96x96"
                    },
                    {
                        src: "assets/icons/android/android-launchericon-72-72.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "72x72"
                    },
                    {
                        src: "assets/icons/android/android-launchericon-48-48.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "48x48"
                    },
                    {
                        src: "assets/icons/ios/16.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "16x16"
                    },
                    {
                        src: "assets/icons/ios/20.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "20x20"
                    },
                    {
                        src: "assets/icons/ios/29.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "29x29"
                    },
                    {
                        src: "assets/icons/ios/32.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "32x32"
                    },
                    {
                        src: "assets/icons/ios/40.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "40x40"
                    },
                    {
                        src: "assets/icons/ios/50.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "50x50"
                    },
                    {
                        src: "assets/icons/ios/57.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "57x57"
                    },
                    {
                        src: "assets/icons/ios/58.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "58x58"
                    },
                    {
                        src: "assets/icons/ios/60.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "60x60"
                    },
                    {
                        src: "assets/icons/ios/64.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "64x64"
                    },
                    {
                        src: "assets/icons/ios/72.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "72x72"
                    },
                    {
                        src: "assets/icons/ios/76.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "76x76"
                    },
                    {
                        src: "assets/icons/ios/80.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "80x80"
                    },
                    {
                        src: "assets/icons/ios/87.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "87x87"
                    },
                    {
                        src: "assets/icons/ios/100.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "100x100"
                    },
                    {
                        src: "assets/icons/ios/114.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "114x114"
                    },
                    {
                        src: "assets/icons/ios/120.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "120x120"
                    },
                    {
                        src: "assets/icons/ios/128.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "128x128"
                    },
                    {
                        src: "assets/icons/ios/144.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "144x144"
                    },
                    {
                        src: "assets/icons/ios/152.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "152x152"
                    },
                    {
                        src: "assets/icons/ios/167.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "167x167"
                    },
                    {
                        src: "assets/icons/ios/180.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "180x180"
                    },
                    {
                        src: "assets/icons/ios/192.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "192x192"
                    },
                    {
                        src: "assets/icons/ios/256.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "256x256"
                    },
                    {
                        src: "assets/icons/ios/512.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "512x512"
                    },
                    {
                        src: "assets/icons/ios/1024.png",
                        type: "image/png",
                        purpose: "maskable",
                        sizes: "1024x1024"
                    }
                ],
                screenshots: [
                    {
                        src: "/assets/screenshots/manifest-mobile.png",
                        sizes: "780x1688",
                        type: "image/png",
                        form_factor: "narrow",
                        label: "Today: your cycle and forecast"
                    },
                    {
                        src: "/assets/screenshots/manifest-desktop.png",
                        sizes: "1280x820",
                        type: "image/png",
                        form_factor: "wide",
                        label: "Calendar with predicted days"
                    }
                ],
            }
        })
    ],
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src', import.meta.url))
        }
    },
    // Ensure the base path is '/' for serving from the Flask backend
    base: '/',
    server: { // Ensure 'server' is a top-level property under defineConfig's object
        port: 5173, // Optional: explicitly set port
        proxy: { // Ensure 'proxy' is a property under 'server'
            '/auth': { // Key should be the path prefix you want to proxy
                target: 'http://127.0.0.1:5000', // The target backend server URL
                changeOrigin: true, // Needed for some APIs, often good practice
                // rewrite: (path) => path.replace(/^\/auth/, '/auth'), // Usually not needed if backend path is the same
            },
            '/periods': {
                target: 'http://127.0.0.1:5000',
                changeOrigin: true,
            },
            '/reports': {
                target: 'http://127.0.0.1:5000',
                changeOrigin: true,
            },
            '/users': {
                target: 'http://127.0.0.1:5000',
                changeOrigin: true,
            },
            '/health': {
                target: 'http://127.0.0.1:5000',
                changeOrigin: true,
            },
            '/events': {
                target: 'http://127.0.0.1:5000',
                changeOrigin: true,
            },
            '/share': {
                target: 'http://127.0.0.1:5000',
                changeOrigin: true,
            },
            '/ha': {
                target: 'http://127.0.0.1:5000',
                changeOrigin: true,
            },
            // only the .ics feed: /calendar itself is an SPA route
            '^/calendar/.+\\.ics$': {
                target: 'http://127.0.0.1:5000',
                changeOrigin: true,
            },
            // Add any other API path prefixes as needed
        }
    }
})