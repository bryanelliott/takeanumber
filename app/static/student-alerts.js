/* Optional effects follow only the private, server-rendered Client View snapshot. */
(() => {
  "use strict";
  const target = document.getElementById("live-state");
  const controls = document.getElementById("student-alert-controls");
  const announcement = document.getElementById("student-announcement");
  if (!target || !controls || !announcement) return;
  const soundButton = document.getElementById("student-sound");
  const vibrationButton = document.getElementById("student-vibration");
  const soundStatus = document.getElementById("student-sound-status");
  const vibrationStatus = document.getElementById("student-vibration-status");
  const Audio = window.AudioContext || window.webkitAudioContext;
  const originalTitle = document.title;
  let audio;
  let tone;
  let soundEnabled = false;
  let vibrationEnabled = false;
  let active = false;
  let entryId = "";
  let seen = new Set();
  let soundAllowed = false;
  let vibrationAllowed = false;
  let policyKey;
  let soundPending = false;
  let policyVersion = 0;

  function soundOff(message = typeof Audio === "function" ? "Sound is off." : "Sound is not supported in this browser. Visual alerts remain.") {
    soundEnabled = false;
    soundButton.setAttribute("aria-pressed", "false");
    soundButton.textContent = "Enable and test sound";
    soundStatus.textContent = message;
    try { tone?.stop(); } catch (_) { /* already finished */ }
  }

  function vibrationOff(message = typeof navigator.vibrate === "function" ? "Vibration is off." : "Vibration is not supported in this browser. Visual alerts remain.") {
    const wasEnabled = vibrationEnabled;
    vibrationEnabled = false;
    vibrationButton.setAttribute("aria-pressed", "false");
    vibrationButton.textContent = "Enable and test vibration";
    vibrationStatus.textContent = message;
    if (wasEnabled) {
      try { navigator.vibrate(0); } catch (_) { /* optional capability */ }
    }
  }

  function playTone() {
    try {
      if (!audio || audio.state !== "running") throw new Error("Audio unavailable");
      const oscillator = audio.createOscillator();
      const gain = audio.createGain();
      oscillator.frequency.value = 660;
      gain.gain.setValueAtTime(0, audio.currentTime);
      gain.gain.linearRampToValueAtTime(0.08, audio.currentTime + 0.015);
      gain.gain.linearRampToValueAtTime(0, audio.currentTime + 0.2);
      oscillator.connect(gain);
      gain.connect(audio.destination);
      oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
      oscillator.start();
      oscillator.stop(audio.currentTime + 0.21);
      tone = oscillator;
      return true;
    } catch (_) {
      soundOff("Sound is blocked or unavailable. Try Enable and test sound again; visual alerts remain.");
      return false;
    }
  }

  function vibrate() {
    try {
      if (navigator.vibrate(150) === false) throw new Error("Vibration unavailable");
      return true;
    } catch (_) {
      vibrationOff("Vibration is unavailable on this device right now. Visual alerts remain.");
      return false;
    }
  }

  soundButton.addEventListener("click", async () => {
    if (!active || !soundAllowed) return;
    if (soundEnabled) { soundOff(); return; }
    const requestedEntry = entryId;
    const requestedPolicy = policyVersion;
    soundPending = true;
    soundButton.disabled = true;
    let timeout;
    try {
      audio = audio && audio.state !== "closed" ? audio : new Audio();
      // resume() is invoked directly from the click, never from a socket callback.
      await Promise.race([
        audio.resume(),
        new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error("Audio timeout")), 3000); }),
      ]);
      if (!active || !soundAllowed || entryId !== requestedEntry || requestedPolicy !== policyVersion) return;
      if (playTone()) {
        soundEnabled = true;
        soundButton.setAttribute("aria-pressed", "true");
        soundButton.textContent = "Turn sound off";
        soundStatus.textContent = "Sound is enabled for this page. Check your device volume if you did not hear the test.";
      }
    } catch (_) {
      soundOff("Sound could not start. Try Enable and test sound again; visual alerts remain.");
    } finally {
      clearTimeout(timeout);
      soundPending = false;
      soundButton.disabled = !soundAllowed || typeof Audio !== "function";
    }
  });

  vibrationButton.addEventListener("click", () => {
    if (!active || !vibrationAllowed) return;
    if (vibrationEnabled) { vibrationOff(); return; }
    if (vibrate()) {
      vibrationEnabled = true;
      vibrationButton.setAttribute("aria-pressed", "true");
      vibrationButton.textContent = "Turn vibration off";
      vibrationStatus.textContent = "Vibration is enabled for this page, where supported by your device.";
    }
  });

  if (typeof Audio !== "function") {
    soundButton.disabled = true;
    soundStatus.textContent = "Sound is not supported in this browser. Visual alerts remain.";
  }
  if (typeof navigator.vibrate !== "function") {
    vibrationButton.disabled = true;
    vibrationStatus.textContent = "Vibration is not supported in this browser. Visual alerts remain.";
  }

  function update(initial = false) {
    const state = target.querySelector("[data-client-status]");
    active = Boolean(state && ["waiting", "serving"].includes(state.dataset.clientStatus));
    controls.hidden = !active;
    const nextPolicy = state?.dataset.alertPolicy || "";
    const policyChanged = policyKey !== undefined && policyKey !== nextPolicy;
    if (policyChanged) policyVersion += 1;
    policyKey = nextPolicy;
    soundAllowed = active && state.dataset.soundAllowed !== "false";
    vibrationAllowed = active && state.dataset.vibrationAllowed !== "false";
    if (!soundAllowed) soundOff(active ? "Sound is disabled by the instructor. Queue status remains available." : undefined);
    if (!vibrationAllowed) vibrationOff(active ? "Vibration is disabled by the instructor. Queue status remains available." : undefined);
    soundButton.disabled = soundPending || !soundAllowed || typeof Audio !== "function";
    vibrationButton.disabled = !vibrationAllowed || typeof navigator.vibrate !== "function";
    const nextEntry = state?.dataset.entryId || "";
    if (nextEntry !== entryId) { entryId = nextEntry; seen = new Set(); }
    const alert = active ? state.dataset.alertState : "";
    if (!["next_up", "serving", "advance_warning"].includes(alert)) {
      announcement.textContent = "";
      document.title = originalTitle;
      if (!active) { soundOff(); vibrationOff(); }
      return;
    }
    const enabled = state.dataset.alertEnabled !== "false";
    const visual = enabled && state.dataset.visualEnabled !== "false";
    const label = alert === "next_up" ? "You're next" : alert === "serving" ? "It's your turn" : "Your turn is approaching";
    document.title = visual ? `${label} — Take A Number` : originalTitle;
    const message = visual ? target.querySelector("[data-alert-message]")?.textContent.trim() || "" : "";
    if (announcement.textContent !== message) announcement.textContent = message;
    if (seen.has(alert)) return;
    seen.add(alert);
    // Initial render is a baseline, not a replay of an old transition.
    if (!initial && !policyChanged && enabled) {
      if (soundEnabled) playTone();
      if (vibrationEnabled) vibrate();
    }
  }

  document.addEventListener("queue:state", () => update());
  window.addEventListener("pagehide", () => {
    active = false;
    announcement.textContent = "";
    document.title = originalTitle;
    soundOff();
    vibrationOff();
    try { audio?.close().catch(() => {}); } catch (_) { /* already closed */ }
  });
  update(true);
})();
