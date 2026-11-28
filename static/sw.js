self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("fetch", (e) => {
  // 네트워크 요청은 그대로 통과 (캐시 충돌 방지)
});