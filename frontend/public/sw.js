// Minimal service worker for PWA installability.
// We intentionally do NOT cache app shell / API responses — installability is
// the only requirement for "Add to Home Screen" prompts on Chrome/Android,
// and aggressive caching would hide deploy updates from beta testers.
//
// If we later want offline support, swap this for a real Workbox setup.

self.addEventListener('install', (event) => {
  // Activate immediately so the next visit uses the new worker.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Take control of all open clients without requiring a reload.
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Pass-through; the network handles every request. Just having a fetch
  // handler registered satisfies the PWA installability heuristic in Chrome.
  // Implicit return = no event.respondWith() = browser uses default fetch.
});
