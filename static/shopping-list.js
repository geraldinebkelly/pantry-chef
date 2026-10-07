// Shopping list: checking an item crosses it off ("I already have this" /
// "already grabbed it"), which only matters to the person shopping - the
// server never needs to know. State is remembered in localStorage, keyed
// by the exact recipe selection (the page's query string), so different
// shopping trips don't bleed into each other.
(function () {
  const container = document.getElementById("shopping-list-items");
  if (!container) return;

  const storageKey = "pantrychef:shopping-checked:" + window.location.search;

  function load() {
    try {
      return JSON.parse(localStorage.getItem(storageKey)) || {};
    } catch (err) {
      return {};
    }
  }

  let checked = load();
  const boxes = container.querySelectorAll("input[type=checkbox][data-key]");

  function applyState(box) {
    const li = box.closest("li");
    const isChecked = !!checked[box.dataset.key];
    box.checked = isChecked;
    if (li) li.classList.toggle("crossed-off", isChecked);
  }

  boxes.forEach((box) => {
    applyState(box);
    box.addEventListener("change", () => {
      if (box.checked) {
        checked[box.dataset.key] = true;
      } else {
        delete checked[box.dataset.key];
      }
      localStorage.setItem(storageKey, JSON.stringify(checked));
      applyState(box);
    });
  });

  const clearButton = document.getElementById("clear-checked");
  if (clearButton) {
    clearButton.addEventListener("click", () => {
      checked = {};
      localStorage.removeItem(storageKey);
      boxes.forEach(applyState);
    });
  }
})();
