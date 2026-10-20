// Cook Mode: switches the Instructions card to one-step-at-a-time view
// (see cook-steps.js) and, where supported, keeps the screen from locking
// via the Screen Wake Lock API. The wake lock is a nice-to-have - step
// mode, timers and read-aloud all work fine without it, so a browser that
// doesn't support it still gets a usable Cook Mode toggle instead of a
// disabled button.
(function () {
  const toggle = document.getElementById("cook-mode-toggle");
  if (!toggle) return;

  const wakeLockSupported = "wakeLock" in navigator;
  let wakeLock = null;
  let active = false;

  function setLabel(isOn) {
    toggle.textContent = isOn ? "🔆 Cook Mode: On" : "🔆 Cook Mode: Off";
    toggle.classList.toggle("active", isOn);
    toggle.setAttribute("aria-pressed", String(isOn));
  }

  async function acquireWakeLock() {
    if (!wakeLockSupported) return;
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      wakeLock.addEventListener("release", () => {
        wakeLock = null;
      });
    } catch (err) {
      // Screen staying awake is a bonus, not a requirement for Cook Mode.
    }
  }

  function releaseWakeLock() {
    if (wakeLock) {
      wakeLock.release();
      wakeLock = null;
    }
  }

  function setActive(isOn) {
    active = isOn;
    setLabel(isOn);
    if (isOn) {
      acquireWakeLock();
    } else {
      releaseWakeLock();
    }
    document.dispatchEvent(new CustomEvent("cookmode:change", { detail: { active: isOn } }));
  }

  toggle.addEventListener("click", () => setActive(!active));

  document.addEventListener("visibilitychange", () => {
    if (active && document.visibilityState === "visible" && !wakeLock) {
      acquireWakeLock();
    }
  });
})();
