/* Queue mutations remain ordinary CSRF-protected forms. Sockets only invalidate. */
(() => {
  "use strict";
  const config = document.getElementById("live-config");
  const target = document.getElementById("live-state");
  const status = document.getElementById("live-status");
  if (!config || !target || !status) return;

  let pending = false;
  let fetching = false;
  let stopped = false;
  let timer;
  let requestController;
  const socket = typeof window.io === "function" ? window.io({
    path: config.dataset.socketPath,
    autoConnect: false,
    auth: (callback) => callback({
      public_code: config.dataset.publicCode,
      view: config.dataset.view,
      csrf_token: config.dataset.csrfToken,
    }),
  }) : null;

  function stop() {
    stopped = true;
    clearInterval(timer);
    requestController?.abort();
    socket?.disconnect();
  }

  function replaceState(html) {
    const next = document.createElement("template");
    next.innerHTML = html;
    const csrf = next.content.querySelector("[data-live-csrf]");
    if (!csrf) throw new Error("Invalid state response");
    config.dataset.csrfToken = csrf.dataset.liveCsrf;

    // A background update must not erase an optional name being typed.
    const name = target.querySelector('input[name="display_name"]');
    const replacement = next.content.querySelector('input[name="display_name"]');
    const focused = name && document.activeElement === name;
    const selection = focused ? [name.selectionStart, name.selectionEnd] : null;
    if (name && replacement) replacement.value = name.value;
    target.replaceChildren(next.content);
    if (focused && replacement) {
      replacement.focus({preventScroll: true});
      replacement.setSelectionRange(...selection);
    }
  }

  async function refresh() {
    if (stopped) return;
    pending = true;
    if (fetching) return;
    fetching = true;
    try {
      while (pending && !stopped) {
        pending = false;
        requestController = new AbortController();
        const timeout = setTimeout(() => requestController.abort(), 10000);
        try {
          const response = await fetch(config.dataset.stateUrl, {
            credentials: "same-origin", cache: "no-store", signal: requestController.signal,
          });
          if (stopped) return;
          if (response.redirected || [401, 403, 404, 409].includes(response.status)) {
            stop();
            target.textContent = "This view is no longer available. Reload the page to continue.";
            status.textContent = "Live updates stopped.";
            return;
          }
          if (!response.ok) throw new Error("State unavailable");
          const html = await response.text();
          if (stopped) return;
          // A newer notice arrived while reading: fetch again, never apply it backwards.
          if (pending) continue;
          replaceState(html);
          status.textContent = socket?.connected
            ? "Live updates connected."
            : "Live connection unavailable; checking for updates periodically.";
          if (socket && !socket.connected && !socket.active) socket.connect();
        } finally {
          clearTimeout(timeout);
        }
      }
    } catch (_) {
      if (!stopped) status.textContent = "Updates unavailable. Use Refresh to try again.";
    } finally {
      fetching = false;
    }
  }

  socket?.on("queue_changed", refresh);
  socket?.on("connect", refresh); // reconcile changes missed before connection/reconnection
  socket?.on("disconnect", () => {
    if (!stopped) status.textContent = "Live connection interrupted; reconnecting.";
  });
  socket?.on("connect_error", () => {
    if (!stopped) status.textContent = "Live connection unavailable; checking periodically.";
  });
  timer = setInterval(refresh, 30000); // also recover from a failed post-commit notification
  window.addEventListener("pagehide", stop); // Exit/disconnect never invokes Leave Queue
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) window.location.reload();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
  if (socket) socket.connect();
  else refresh();
})();
