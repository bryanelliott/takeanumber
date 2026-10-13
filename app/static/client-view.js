/* Progressive enhancement only: identity and queue transitions remain server-owned. */
(() => {
  "use strict";
  const target = document.getElementById("live-state");
  const announcement = document.getElementById("client-announcement");
  if (!target || !announcement) return;
  const state = () => target.querySelector("[data-client-status]");
  let previousMessage = message();
  let focused;
  let pendingForm;
  let pendingTimer;

  function message() {
    const current = state();
    // Next Up / Serving / advance warnings use the existing preference-aware alerts.
    if (!current || current.dataset.alertState) return "";
    return current.querySelector("[data-client-message]")?.textContent.trim() || "";
  }

  function comparable(region) {
    const copy = region.cloneNode(true);
    copy.querySelectorAll('input[name="csrf_token"]').forEach(input => input.value = "");
    copy.querySelectorAll('input[name="display_name"]').forEach(input => input.setAttribute("value", ""));
    copy.querySelectorAll("details").forEach(details => details.removeAttribute("open"));
    return copy.innerHTML;
  }

  document.addEventListener("queue:before-state", () => {
    const active = document.activeElement;
    focused = target.contains(active) ? {
      node: active, key: active.dataset.clientFocus, entry: state()?.dataset.entryId,
    } : null;
  });
  document.addEventListener("queue:render", event => {
    const current = state();
    const next = event.detail.fragment.querySelector("[data-client-status]");
    if (current && next && current.dataset.entryId === next.dataset.entryId) {
      const disclosure = current.querySelector("[data-client-disclosure]");
      const replacement = next.querySelector("[data-client-disclosure]");
      if (disclosure && replacement) replacement.open = disclosure.open;
    }
    if (!current || !next || current.dataset.clientStatus !== next.dataset.clientStatus
        || current.dataset.entryId !== next.dataset.entryId) return;
    const regions = ["session", "primary", "secondary"].map(key => [
      current.querySelector(`[data-client-region="${key}"]`),
      next.querySelector(`[data-client-region="${key}"]`),
    ]);
    if (regions.some(pair => pair.some(region => !region))) return;
    event.preventDefault();

    // A successful background GET must not erase feedback from an invalid form POST.
    const form = current.querySelector('[data-client-form="join"]');
    const nextForm = next.querySelector('[data-client-form="join"]');
    if (form?.querySelector('[aria-invalid="true"], [role="alert"]') && nextForm
        && form.elements.browser_binding.value === nextForm.elements.browser_binding.value) {
      nextForm.replaceWith(form.cloneNode(true));
    }
    for (const [oldRegion, newRegion] of regions) {
      if (comparable(oldRegion) === comparable(newRegion)) continue;
      oldRegion.replaceWith(newRegion);
    }
    for (const attribute of next.attributes) current.setAttribute(attribute.name, attribute.value);
    // Refresh CSRF in place even when all visible content is unchanged.
    current.querySelectorAll('input[name="csrf_token"]').forEach(input => {
      input.value = next.dataset.liveCsrf;
    });
  });
  document.addEventListener("queue:state", () => {
    if (focused && !focused.node.isConnected) {
      const control = focused.entry === state()?.dataset.entryId && focused.key
        ? target.querySelector(`[data-client-focus="${focused.key}"]`) : null;
      (control || target.querySelector("[data-client-fallback]") || target)
        .focus({preventScroll: true});
    }
    focused = null;
    const nextMessage = message();
    if (nextMessage !== previousMessage) announcement.textContent = nextMessage;
    previousMessage = nextMessage;
    if (pendingForm) showPending();
  });

  function showPending() {
    target.querySelectorAll("[data-client-form]").forEach(form => {
      form.setAttribute("aria-busy", "true");
      const button = form.querySelector('[type="submit"]');
      if (!button) return;
      button.dataset.originalLabel ||= button.textContent;
      button.disabled = true;
      if (form.dataset.clientForm === pendingForm) {
        button.textContent = pendingForm === "join" ? "Joining…" : "Leaving…";
      }
    });
  }
  function resetSubmission() {
    clearTimeout(pendingTimer);
    pendingForm = null;
    target.querySelectorAll('[data-client-form][aria-busy]').forEach(form => {
      form.removeAttribute("aria-busy");
      const button = form.querySelector('[type="submit"]');
      if (!button) return;
      button.disabled = false;
      if (button.dataset.originalLabel) button.textContent = button.dataset.originalLabel;
      delete button.dataset.originalLabel;
    });
  }
  target.addEventListener("submit", event => {
    if (!event.target.matches("[data-client-form]") || event.defaultPrevented) return;
    if (pendingForm) { event.preventDefault(); return; }
    pendingForm = event.target.dataset.clientForm;
    showPending();
    // Restore controls if navigation stalls; never retry or create a request automatically.
    pendingTimer = setTimeout(resetSubmission, 10000);
  });
  window.addEventListener("pageshow", resetSubmission);
})();
