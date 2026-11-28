// Installed gardens require a network connection. Keep lesson and sign-in
// responses on the server so access changes take effect on the next request.
self.addEventListener("fetch", event => {
  if (event.request.mode === "navigate") event.respondWith(fetch(event.request));
});
