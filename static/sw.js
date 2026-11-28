const CACHE_NAME = "smart-assistant-v1";

self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (e) => {
  // GET 요청에 대해서만 네트워크 응답 반환 (PWA 설치 필수 조건 충족)
  if (e.request.method !== "GET") return;
  e.respondWith(
    fetch(e.request).catch(() => {
      return new Response("오프라인 상태입니다.", {
        status: 503,
        statusText: "Service Unavailable"
      });
    })
  );
});