/* Optional form feedback; native validation and CSRF-protected POSTs remain authoritative. */
(() => {
  "use strict";
  const toggles = document.querySelectorAll("[data-password-toggle]");
  function conceal(button) {
    const input = document.getElementById(button.dataset.passwordToggle);
    if (!input) return;
    input.type = "password";
    button.textContent = "Show";
    button.setAttribute("aria-label", button.dataset.showLabel);
  }
  toggles.forEach(button => {
    const input = document.getElementById(button.dataset.passwordToggle);
    if (!input || input.type !== "password") return;
    button.dataset.showLabel = button.getAttribute("aria-label");
    button.hidden = false;
    button.addEventListener("click", () => {
      if (input.type === "text") { conceal(button); return; }
      input.type = "text";
      button.textContent = "Hide";
      button.setAttribute("aria-label", button.dataset.showLabel.replace(/^Show /, "Hide "));
    });
  });
  document.querySelectorAll("form[data-submit-feedback]").forEach(form => {
    const button = form.querySelector('[type="submit"]');
    if (!button) return;
    let pending = false;
    let timer;
    let original;
    function reset() {
      clearTimeout(timer);
      pending = false;
      form.removeAttribute("aria-busy");
      button.disabled = false;
      if (original) button.replaceChildren(...original);
      original = null;
    }
    form.addEventListener("submit", event => {
      if (event.defaultPrevented) return;
      if (pending) { event.preventDefault(); return; }
      toggles.forEach(conceal);
      pending = true;
      original = [...button.childNodes];
      button.textContent = form.dataset.submitFeedback;
      button.disabled = true;
      form.setAttribute("aria-busy", "true");
      // A stalled navigation must not permanently lock the form; never retry automatically.
      timer = setTimeout(reset, 10000);
    });
    window.addEventListener("pageshow", reset);
  });
  window.addEventListener("pagehide", () => toggles.forEach(conceal));
})();
