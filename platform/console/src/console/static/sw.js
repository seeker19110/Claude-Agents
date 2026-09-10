/* Service worker của console — cố ý là cái nhỏ nhất đủ để cài được thành app.
 *
 * KHÔNG cache hai thứ, và đó là toàn bộ điểm cần soi khi đọc file này:
 *
 *   1. `/api/*` — dữ liệu sống. Console tồn tại để nói đúng cái đang có trong bus; phục vụ
 *      một bản trả lời cũ từ cache là đúng thứ tệ nhất mà mặt kính này có thể làm. Kể cả
 *      `/api/stream` (SSE) cũng không được đi qua đây: một luồng không bao giờ kết thúc mà
 *      bị cache là treo.
 *   2. `/` — trang HTML mang `window.__CONSOLE__.token`, mà token sinh MỚI mỗi lần chạy
 *      server. Cache trang là lần chạy sau nhận token cũ và ăn 401 toàn tập.
 *
 * Còn lại chỉ có icon là đáng cache, và cũng chỉ để icon không nháy khi mở app.
 * Console không dùng được khi server cục bộ chưa chạy, nên "chạy offline" không phải mục tiêu.
 */
"use strict";

const SHELL = "console-shell-v1";
const ASSETS = ["/static/icon-192.png", "/static/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== SHELL).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;              // POST /api/gate/decide đi thẳng
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;        // (1) dữ liệu sống
  if (url.pathname === "/") return;                    // (2) HTML mang token phiên
  if (!ASSETS.includes(url.pathname)) return;
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});
