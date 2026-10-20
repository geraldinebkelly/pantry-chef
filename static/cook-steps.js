// Step-by-step Cook Mode: shows one instruction at a time (larger, easier
// to read mid-cook), with a per-step timer (auto-suggested from a duration
// mentioned in the step, e.g. "5 to 7 minutes") and a read-aloud button.
// Activated/deactivated by the cookmode:change event from cook-mode.js -
// this file doesn't touch the wake lock at all, so it works the same
// whether or not that's supported.
(function () {
  const dataEl = document.getElementById("recipe-instructions-data");
  const container = document.getElementById("cook-steps");
  const fullText = document.getElementById("instructions-full");
  if (!dataEl || !container || !fullText) return;

  // PDF-sourced instructions keep the source's own line wrapping, so a
  // single step is often spread across several raw lines (only the first
  // of which starts with its number) - group by the numbered marker
  // rather than assuming one line = one step. Falls back to one step per
  // line when there's no (or only one) numbered marker to group by, the
  // convention for manually typed instructions.
  function parseSteps(text) {
    const lines = text.replace(/\r\n?/g, "\n").split("\n").map((l) => l.trim());
    const numberedRe = /^\d+[.)]\s+/;
    const numberedCount = lines.filter((l) => l && numberedRe.test(l)).length;

    if (numberedCount >= 2) {
      const grouped = [];
      for (const line of lines) {
        if (!line) continue;
        if (numberedRe.test(line)) {
          grouped.push(line.replace(numberedRe, ""));
        } else if (grouped.length) {
          grouped[grouped.length - 1] += " " + line;
        }
      }
      return grouped;
    }
    return lines.filter(Boolean).map((l) => l.replace(numberedRe, ""));
  }

  const raw = JSON.parse(dataEl.textContent || '""');
  const steps = parseSteps(raw);

  const counterEl = document.getElementById("cook-step-counter");
  const textEl = document.getElementById("cook-step-text");
  const prevBtn = document.getElementById("cook-step-prev");
  const nextBtn = document.getElementById("cook-step-next");
  const readBtn = document.getElementById("cook-step-read");
  const timerEl = document.getElementById("cook-step-timer");

  if (!steps.length || !counterEl || !textEl || !prevBtn || !nextBtn || !readBtn || !timerEl) {
    return;
  }

  const speechSupported = "speechSynthesis" in window;
  if (!speechSupported) readBtn.hidden = true;

  let current = 0;
  // Keyed by step index, so a running timer survives switching steps (or
  // toggling Cook Mode off) - the oven doesn't care whether the tab is
  // looking at that step.
  const timers = new Map();

  // Checked in this order so a mixed number or fraction ("1 1/2 minutes",
  // "1/2 hour") is caught before the plain-number pattern below can
  // mistake its denominator for a standalone duration ("1/2 minutes" ->
  // wrongly reading as "2 minutes").
  const MIXED_RE = /(\d+)\s+(\d+)\/(\d+)\s*(hours?|hrs?|minutes?|mins?)\b/i;
  const FRACTION_RE = /(\d+)\/(\d+)\s*(hours?|hrs?|minutes?|mins?)\b/i;
  const RANGE_RE = /(\d+)\s*(?:to|-|–|—)\s*(\d+)\s*(hours?|hrs?|minutes?|mins?)\b/i;
  const SINGLE_RE = /(\d+)\s*(hours?|hrs?|minutes?|mins?)\b/i;

  function formatAmount(n) {
    return Number.isInteger(n) ? String(n) : n.toFixed(1);
  }

  function toResult(n, unit) {
    const isHours = unit.toLowerCase().startsWith("h");
    return { seconds: Math.round(n * (isHours ? 3600 : 60)), label: `${formatAmount(n)} ${isHours ? "hr" : "min"}` };
  }

  function detectDuration(text) {
    let m = MIXED_RE.exec(text);
    if (m) return toResult(parseInt(m[1], 10) + parseInt(m[2], 10) / parseInt(m[3], 10), m[4]);

    m = FRACTION_RE.exec(text);
    if (m) return toResult(parseInt(m[1], 10) / parseInt(m[2], 10), m[3]);

    m = RANGE_RE.exec(text);
    if (m) return toResult(Math.max(parseInt(m[1], 10), parseInt(m[2], 10)), m[3]);

    m = SINGLE_RE.exec(text);
    if (m) return toResult(parseInt(m[1], 10), m[2]);

    return null;
  }

  function formatClock(totalSeconds) {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      osc.start();
      osc.stop(ctx.currentTime + 0.6);
      osc.onended = () => ctx.close();
    } catch (err) {
      // No Web Audio support - the visual "Done!" state still shows.
    }
  }

  function clearTimer(index) {
    const t = timers.get(index);
    if (t && t.intervalId) clearInterval(t.intervalId);
    timers.delete(index);
  }

  function startTimer(index, seconds, label) {
    clearTimer(index);
    const t = { remaining: seconds, label, done: false };
    t.intervalId = setInterval(() => {
      t.remaining -= 1;
      if (t.remaining <= 0) {
        clearInterval(t.intervalId);
        t.intervalId = null;
        t.done = true;
        beep();
      }
      if (index === current) renderTimer(index);
    }, 1000);
    timers.set(index, t);
    renderTimer(index);
  }

  function renderTimer(index) {
    timerEl.innerHTML = "";
    const t = timers.get(index);

    if (t && !t.done) {
      const clock = document.createElement("span");
      clock.className = "cook-timer-clock";
      clock.textContent = `⏱ ${formatClock(Math.max(t.remaining, 0))}`;
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "btn-secondary";
      cancel.textContent = "Cancel";
      cancel.addEventListener("click", () => {
        clearTimer(index);
        renderTimer(index);
      });
      timerEl.append(clock, cancel);
      return;
    }

    if (t && t.done) {
      const done = document.createElement("span");
      done.className = "cook-timer-done";
      done.textContent = `⏰ ${t.label} timer done!`;
      const dismiss = document.createElement("button");
      dismiss.type = "button";
      dismiss.className = "btn-secondary";
      dismiss.textContent = "Dismiss";
      dismiss.addEventListener("click", () => {
        clearTimer(index);
        renderTimer(index);
      });
      timerEl.append(done, dismiss);
      return;
    }

    const detected = detectDuration(steps[index]);
    if (detected) {
      const startBtn = document.createElement("button");
      startBtn.type = "button";
      startBtn.className = "btn-secondary";
      startBtn.textContent = `Start timer (${detected.label})`;
      startBtn.addEventListener("click", () => startTimer(index, detected.seconds, detected.label));
      timerEl.append(startBtn);
    }

    const customInput = document.createElement("input");
    customInput.type = "number";
    customInput.min = "1";
    customInput.placeholder = "min";
    customInput.className = "cook-timer-custom-input";
    const customBtn = document.createElement("button");
    customBtn.type = "button";
    customBtn.className = "btn-secondary";
    customBtn.textContent = "Start custom timer";
    customBtn.addEventListener("click", () => {
      const minutes = parseInt(customInput.value, 10);
      if (minutes > 0) startTimer(index, minutes * 60, `${minutes} min`);
    });
    timerEl.append(customInput, customBtn);
  }

  function stopSpeaking() {
    if (speechSupported) window.speechSynthesis.cancel();
    readBtn.textContent = "🔊 Read aloud";
  }

  function renderStep(index) {
    current = index;
    counterEl.textContent = `Step ${index + 1} of ${steps.length}`;
    textEl.textContent = steps[index];
    prevBtn.disabled = index === 0;
    nextBtn.disabled = index === steps.length - 1;
    stopSpeaking();
    renderTimer(index);
  }

  prevBtn.addEventListener("click", () => {
    if (current > 0) renderStep(current - 1);
  });
  nextBtn.addEventListener("click", () => {
    if (current < steps.length - 1) renderStep(current + 1);
  });

  readBtn.addEventListener("click", () => {
    if (!speechSupported) return;
    if (window.speechSynthesis.speaking) {
      stopSpeaking();
      return;
    }
    const utterance = new SpeechSynthesisUtterance(steps[current]);
    utterance.onend = () => {
      readBtn.textContent = "🔊 Read aloud";
    };
    readBtn.textContent = "⏹ Stop reading";
    window.speechSynthesis.speak(utterance);
  });

  document.addEventListener("cookmode:change", (e) => {
    container.hidden = !e.detail.active;
    fullText.hidden = e.detail.active;
    if (e.detail.active) {
      renderStep(current);
    } else {
      stopSpeaking();
    }
  });
})();
