// Service worker: installable app + offline access to what you last saw.
//
// - Built assets (/assets/*, hashed filenames): cache-first, they never change.
// - API GETs: network-first, falling back to the last cached response when offline, so
//   predictions are never stale while online.
// - Page navigations: network-first, falling back to the cached app shell.
// POST/PUT (simulations, picks) are never cached.

const VERSION = 'v3' // bump to drop old caches (v3: standings, circuit maps)
const SHELL = `shell-${VERSION}`
const ASSETS = `assets-${VERSION}`
const API = `api-${VERSION}`

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((c) => c.addAll(['/', '/manifest.webmanifest', '/icons/icon-192.png']))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  const keep = new Set([SHELL, ASSETS, API])
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !keep.has(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName)
  try {
    const response = await fetch(request)
    if (response.ok) cache.put(request, response.clone())
    return response
  } catch (err) {
    const cached = await cache.match(request)
    if (cached) return cached
    throw err
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(ASSETS)
  const cached = await cache.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) cache.put(request, response.clone())
  return response
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request, API))
  } else if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/')) {
    event.respondWith(cacheFirst(request))
  } else if (request.mode === 'navigate') {
    event.respondWith(
      networkFirst(request, SHELL).catch(() => caches.match('/', { cacheName: SHELL })),
    )
  }
})
