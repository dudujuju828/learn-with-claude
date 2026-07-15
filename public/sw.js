/* Offline support. The app is local-first (trees render from localStorage),
   so all this worker has to do is keep the shell and fonts openable with no
   network. Three rules:
   - /api/* is never touched — auth, model calls, and sync stay live-only.
   - navigations are network-first: a deploy lands the moment you're online;
     offline falls back to the cached shell.
   - static assets and fonts are cache-first with a background refresh. */

const CACHE = "lwc-shell-v1";
const SHELL = ["/", "/icon.svg", "/apple-touch-icon.png", "/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;

  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          const copy = r.clone();
          caches.open(CACHE).then((c) => c.put("/", copy)).catch(() => {});
          return r;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }

  // same-origin assets + cross-origin fonts (opaque responses are fine)
  e.respondWith(
    caches.match(e.request).then((hit) => {
      const refresh = fetch(e.request)
        .then((r) => {
          if (r.ok || r.type === "opaque") {
            const copy = r.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
          }
          return r;
        })
        .catch(() => hit);
      return hit || refresh;
    })
  );
});
