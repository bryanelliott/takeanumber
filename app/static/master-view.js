/* Presentation and accessibility only; the server remains the queue authority. */
(() => {
  "use strict";
  const toggle = document.getElementById("presentation-toggle");
  const target = document.getElementById("live-state");
  const join = document.getElementById("master-join");
  const announcement = document.getElementById("master-announcement");
  if (!toggle || !target || !announcement) return;
  const preferenceKey = `master-presentation:${location.pathname}`;
  let lastSummary = "";
  let focusBefore = null;

  function present(enabled) {
    document.body.classList.toggle("is-presenting", enabled);
    toggle.setAttribute("aria-pressed", String(enabled));
    toggle.textContent = enabled ? "Exit Presentation Mode" : "Presentation Mode";
    try { sessionStorage.setItem(preferenceKey, enabled ? "on" : "off"); } catch (_) { /* Optional. */ }
  }

  function reconcile(initial = false) {
    const toggleFocused = document.activeElement === toggle;
    const state = target.querySelector("[data-master-status]");
    target.classList.toggle("is-unavailable", !state);
    const active = state?.dataset.masterStatus === "active";
    // The QR lives outside the refreshed fragment; remove it on end/auth loss.
    if (!active && join) join.remove();
    toggle.hidden = !active;
    if (!active) present(false);
    const summary = state?.querySelector("[data-master-summary]")?.textContent.trim()
      || "This view is no longer available. Reload the page to continue.";
    if (!initial && summary !== lastSummary) announcement.textContent = summary;
    lastSummary = summary;
    if (focusBefore) {
      const candidates = [...target.querySelectorAll("[data-master-focus]")];
      const replacement = candidates.find((node) => node.dataset.masterFocus === focusBefore.key
        && (node.form?.elements.entry_id?.value || "") === focusBefore.entry);
      // Never transfer focus to a Done button for a different request.
      const destination = replacement || target.querySelector("[data-focus-fallback]") || target;
      destination?.focus({preventScroll: true});
      focusBefore = null;
    } else if (!active && toggleFocused) {
      (target.querySelector("[data-focus-fallback]") || target).focus({preventScroll: true});
    }
  }

  toggle.addEventListener("click", () => present(toggle.getAttribute("aria-pressed") !== "true"));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("is-presenting")) {
      present(false);
      toggle.focus({preventScroll: true});
    }
  });
  document.addEventListener("queue:before-state", () => {
    const focused = document.activeElement;
    focusBefore = target.contains(focused) && focused.dataset.masterFocus
      ? {key: focused.dataset.masterFocus, entry: focused.form?.elements.entry_id?.value || ""}
      : null;
  });
  document.addEventListener("queue:state", () => reconcile());
  try { present(sessionStorage.getItem(preferenceKey) === "on"); } catch (_) { present(false); }
  reconcile(true);
})();
