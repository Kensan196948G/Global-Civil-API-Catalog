/* Service worker: read-only offline cache for the catalog UI and data.
 * Writes (/auth/*, /api/v1/*) are never cached. */
const CACHE = "gc-api-catalog-v1";
const CORE = ["/", "/static/index.html", "/static/app.js", "/static/styles.css"];
const DATA = [
  "/api/catalog",
  "/api/summary",
  "/api/verification",
  "/api/export",
  "/api/live-map",
  "/api/metadata",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(CORE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (CORE.includes(url.pathname) || DATA.includes(url.pathname)) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request)),
    );
  }
});
