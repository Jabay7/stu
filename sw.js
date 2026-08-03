/* Offline support. Bump CACHE when the shell changes so old copies get evicted. */

const CACHE = "stu-v1";
const SHELL = [
  ".",
  "index.html",
  "styles.css",
  "app.js",
  "manifest.webmanifest",
  "icons/icon-192.png",
  "icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  // Network-first everywhere, cache as the offline fallback.
  //
  // A cache-first shell is the usual PWA advice, but it means a deployed CSS or
  // JS change stays invisible until the CACHE constant is bumped -- easy to
  // forget, and it silently serves stale code to everyone who already visited.
  // Network-first costs a few ms on a live connection and keeps the app correct.
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
        }
        return res;
      })
      .catch(() =>
        caches.match(request, { ignoreSearch: true }).then(
          (hit) => hit || caches.match("index.html")
        )
      )
  );
});
