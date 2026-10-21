// Search/filter the "Recipe pool" checklist on the Plan a Week page.
// Purely client-side: filtering only ever shows/hides rows, it never
// removes a checkbox from the form, so a selection made before narrowing
// the list (or scrolled out of view) still submits correctly.
(function () {
  const searchInput = document.getElementById("pool-search");
  const items = Array.from(document.querySelectorAll(".pool-item"));
  const noMatches = document.getElementById("pool-no-matches");
  const selectedCount = document.getElementById("pool-selected-count");
  if (!searchInput || !items.length) return;

  const active = { cuisine: "", course: "" };

  function applyFilters() {
    const query = searchInput.value.trim().toLowerCase();
    let visibleCount = 0;

    items.forEach((item) => {
      const matchesSearch = !query || item.dataset.title.includes(query);
      const matchesCuisine = !active.cuisine || item.dataset.cuisine.includes(active.cuisine);
      const matchesCourse = !active.course || item.dataset.course.includes(active.course);
      const visible = matchesSearch && matchesCuisine && matchesCourse;
      item.hidden = !visible;
      if (visible) visibleCount += 1;
    });

    if (noMatches) noMatches.hidden = visibleCount > 0;
  }

  function updateSelectedCount() {
    if (!selectedCount) return;
    const checked = items.filter((item) => item.querySelector("input").checked).length;
    selectedCount.textContent = `${checked} of ${items.length} selected`;
  }

  searchInput.addEventListener("input", applyFilters);

  document.querySelectorAll("[data-pool-filter]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const group = chip.dataset.poolFilter;
      const value = chip.dataset.value.toLowerCase();
      active[group] = value;
      document.querySelectorAll(`[data-pool-filter="${group}"]`).forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.value.toLowerCase() === value);
      });
      applyFilters();
    });
  });

  items.forEach((item) => item.querySelector("input").addEventListener("change", updateSelectedCount));

  applyFilters();
  updateSelectedCount();
})();
