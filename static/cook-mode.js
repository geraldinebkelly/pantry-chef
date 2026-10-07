// Cook Mode: keeps the screen from locking while a recipe is open, using
// the Screen Wake Lock API. The browser releases the lock automatically
// whenever the tab is hidden (switching apps, locking the phone) - if Cook
// Mode is still toggled on, it's re-requested once the tab is visible
// again, since the lock itself can't survive that.
(function () {
  const toggle = document.getElementById("cook-mode-toggle");
  if (!toggle) return;

  if (!("wakeLock" in navigator)) {
    toggle.disabled = true;
    toggle.textContent = "🔆 Cook Mode (not supported in this browser)";
    return;
  }

  let wakeLock = null;
  let wantsActive = false;

  function setLabel(isOn) {
    toggle.textContent = isOn ? "🔆 Cook Mode: On" : "🔆 Cook Mode: Off";
    toggle.classList.toggle("active", isOn);
    toggle.setAttribute("aria-pressed", String(isOn));
  }

  async function acquire() {
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      setLabel(true);
      wakeLock.addEventListener("release", () => {
        wakeLock = null;
      });
    } catch (err) {
      wantsActive = false;
      setLabel(false);
    }
  }

  function release() {
    wantsActive = false;
    if (wakeLock) {
      wakeLock.release();
      wakeLock = null;
    }
    setLabel(false);
  }

  toggle.addEventListener("click", () => {
    if (wantsActive) {
      release();
    } else {
      wantsActive = true;
      acquire();
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (wantsActive && document.visibilityState === "visible" && !wakeLock) {
      acquire();
    }
  });
})();
