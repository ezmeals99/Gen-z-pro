const CACHE_NAME = 'genz-pro-v1';
// App එක offline උනත් ලෝඩ් වෙන්න ඕන කරන files මෙතනට දානවා
const urlsToCache = [
  '/',
  '/index.html',
  '/manifest.json',
  'https://cdn-icons-png.flaticon.com/512/825/825590.png'
];

// 1. Install Event - Files ටික phone එකේ cache එකට දාගන්නවා
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

// 2. Fetch Event - ඊළඟ පාර app එකට එද්දී cache එකෙන් ඉක්මනට load කරලා දෙනවා
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request);
      }
    )
  );
});