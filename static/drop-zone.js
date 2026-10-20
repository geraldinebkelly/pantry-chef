// Drag-and-drop for the PDF upload field. Without explicitly handling
// "drop", the browser's default action for a dropped file is to open it
// in a new tab - so every drag/drop event here is preventDefault()'d, and
// the dropped files are assigned to the input manually via DataTransfer.
(function () {
  const zone = document.getElementById("pdf-drop-zone");
  const input = document.getElementById("pdf_files");
  const fileList = document.getElementById("pdf-file-list");
  if (!zone || !input) return;

  function renderFileList() {
    fileList.innerHTML = "";
    Array.from(input.files).forEach((file) => {
      const li = document.createElement("li");
      li.textContent = file.name;
      fileList.appendChild(li);
    });
  }

  ["dragenter", "dragover"].forEach((evt) => {
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.add("dragover");
    });
  });

  ["dragleave", "dragend"].forEach((evt) => {
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
    });
  });

  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    e.stopPropagation();
    zone.classList.remove("dragover");
    if (e.dataTransfer && e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });

  input.addEventListener("change", renderFileList);

  // Belt-and-braces: a file dropped just outside the zone (its border or
  // the page around it) would otherwise still navigate the whole tab to
  // that file - stop that everywhere, not just inside the zone.
  ["dragover", "drop"].forEach((evt) => {
    window.addEventListener(evt, (e) => e.preventDefault());
  });
})();

// Parsing a PDF (or several) takes a few seconds, with no visual feedback
// otherwise - easy to mistake for nothing happening and click again,
// which is exactly what created duplicate draft recipes during testing.
// Disabling the button also blocks that second submission outright, not
// just the spinner for show.
[
  ["import-form", "import-submit", "import-wait-hint"],
  ["url-import-form", "url-import-submit", "url-import-wait-hint"],
].forEach(([formId, buttonId, hintId]) => {
  const form = document.getElementById(formId);
  const button = document.getElementById(buttonId);
  const waitHint = document.getElementById(hintId);
  if (!form || !button) return;

  form.addEventListener("submit", () => {
    button.disabled = true;
    button.classList.add("loading");
    if (waitHint) waitHint.style.display = "block";
  });
});
