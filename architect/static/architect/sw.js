/**
 * AIBPMN Architect — Progressive Web App Service Worker
 *
 * ВАЖНО: Воркер путей и навигации намеренно НЕ переносится в SW,
 * чтобы не нарушать CSRF-авторизацию, сессии и серверный роутинг Django.
 * SW обрабатывает ИСКЛЮЧИТЕЛЬНО кеширование статических файлов (CSS, JS, иконки, шрифты).
 */

const CACHE_NAME = 'aibpmn-static-v7';

// Предварительно кешируемые статические ресурсы
const PRECACHE_ASSETS = [
  '/static/architect/css/app.css',
  '/static/architect/vendor/diagram-js.css',
  '/static/architect/vendor/bpmn-js.css',
  '/static/architect/vendor/bpmn-embedded.css',
  '/static/architect/vendor/prism.min.css',
  '/static/architect/icons/favicon.svg',
  '/static/architect/icons/favicon-32x32.png',
  '/static/architect/icons/icon-192.png',
  '/static/architect/icons/icon-512.png',
  '/manifest.json'
];

// Установка: предварительное кеширование критических статических ресурсов
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        return cache.addAll(PRECACHE_ASSETS).catch((err) => {
          console.warn('[SW] Precache partial error (ignored):', err);
        });
      })
      .then(() => self.skipWaiting())
  );
});

// Активация: удаление старых версий кеша
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Перехват сетевых запросов: СТРОГО только статика, НИКАКОГО вмешательства в пути и CSRF Django
self.addEventListener('fetch', (event) => {
  const request = event.request;

  // 1. Игнорируем любые не-GET запросы (POST, PUT, DELETE, PATCH содержат CSRF-токены и мутации)
  if (request.method !== 'GET') {
    return;
  }

  // 2. Игнорируем навигационные запросы браузера (HTML страниц).
  // Django должен ВСЕГДА отдавать актуальный HTML с валидным CSRF-токеном и авторизацией!
  if (request.mode === 'navigate') {
    return;
  }

  const url = new URL(request.url);

  // 3. Игнорируем любые обращения к API, админке, аутентификации и CSRF-эндпоинтам
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/admin/') ||
    url.pathname.startsWith('/auth/') ||
    url.pathname.includes('csrf')
  ) {
    return;
  }

  // 4. Кешируем только статические файлы (CSS, JS, изображения, шрифты, манифест)
  const isStaticResource = (
    url.pathname.startsWith('/static/') ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.css') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.jpg') ||
    url.pathname.endsWith('.jpeg') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.ico') ||
    url.pathname.endsWith('.woff2') ||
    url.pathname.endsWith('.woff') ||
    url.pathname.endsWith('.ttf') ||
    url.pathname === '/manifest.json'
  );

  if (!isStaticResource) {
    return;
  }

  // Стратегия Stale-While-Revalidate для статических файлов
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      const networkFetch = fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, clone);
            });
          }
          return networkResponse;
        })
        .catch(() => {
          return cachedResponse;
        });

      return cachedResponse || networkFetch;
    })
  );
});

