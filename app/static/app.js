// SmartDent page helpers: table search, table sorting, X-ray zoom, AI boxes,
// marking findings the AI missed, drag-and-drop upload and the "AI is reading the X-ray" loading page.
// Plain JavaScript, no libraries. Each part only runs if its elements are on the page.

// ---------- 1. Search: <input data-filter="tableId"> hides rows that don't match ----------
document.querySelectorAll("input[data-filter]").forEach((input) => {
  const table = document.getElementById(input.dataset.filter);
  const empty = document.getElementById(input.dataset.filter + "-none");
  input.addEventListener("input", () => {
    const words = input.value.trim().toLowerCase();
    let shown = 0;
    table.querySelectorAll("tbody tr").forEach((row) => {
      const match = row.textContent.toLowerCase().includes(words);
      row.hidden = !match;
      if (match) shown++;
    });
    if (empty) empty.hidden = shown > 0;
  });
});

// ---------- 2. Sorting: click a <th data-sort> to sort by that column ----------
// A cell can give a hidden sort value with data-value (e.g. a date as 2026-10-17).
document.querySelectorAll("table.sortable").forEach((table) => {
  table.querySelectorAll("th[data-sort]").forEach((th, _) => {
    th.addEventListener("click", () => {
      const column = Array.from(th.parentNode.children).indexOf(th);
      const ascending = th.dataset.dir !== "asc";
      table.querySelectorAll("th[data-sort]").forEach((other) => delete other.dataset.dir);
      th.dataset.dir = ascending ? "asc" : "desc";
      const body = table.querySelector("tbody");
      const rows = Array.from(body.querySelectorAll("tr"));
      const valueOf = (row) => {
        const cell = row.children[column];
        return (cell.dataset.value ?? cell.textContent).trim();
      };
      const numeric = th.dataset.sort === "number";
      rows.sort((a, b) => {
        const x = valueOf(a), y = valueOf(b);
        const order = numeric ? (Number(x) || 0) - (Number(y) || 0) : x.localeCompare(y);
        return ascending ? order : -order;
      });
      rows.forEach((row) => body.appendChild(row));
    });
  });
});

// ---------- 3. X-ray zoom: click the X-ray, then scroll to zoom and drag to move ----------
const zoomable = document.querySelector("img[data-zoom]");
const viewer = document.getElementById("zoom-viewer");
if (zoomable && viewer) {
  const big = viewer.querySelector("img");
  let scale = 1, x = 0, y = 0, dragging = null;
  const apply = () => { big.style.transform = `translate(${x}px, ${y}px) scale(${scale})`; };
  const reset = () => { scale = 1; x = 0; y = 0; apply(); };

  zoomable.addEventListener("click", () => {
    // Boxes on: zoom the copy with boxes drawn in. Boxes off: the plain X-ray.
    const toggle = document.getElementById("show-boxes");
    big.src = toggle && zoomable.dataset.annotated
      ? (toggle.checked ? zoomable.dataset.annotated : zoomable.dataset.original)
      : zoomable.src;
    reset();
    viewer.hidden = false;
  });
  viewer.querySelector("[data-close]").addEventListener("click", () => { viewer.hidden = true; });
  viewer.querySelector("[data-reset]").addEventListener("click", reset);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") viewer.hidden = true; });

  viewer.addEventListener("wheel", (e) => {
    e.preventDefault();
    scale = Math.min(8, Math.max(1, scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
    if (scale === 1) { x = 0; y = 0; }
    apply();
  }, { passive: false });
  big.addEventListener("mousedown", (e) => { e.preventDefault(); dragging = { sx: e.clientX - x, sy: e.clientY - y }; });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    x = e.clientX - dragging.sx; y = e.clientY - dragging.sy; apply();
  });
  window.addEventListener("mouseup", () => { dragging = null; });
}

// ---------- 4. AI boxes over the X-ray, linked to the findings list ----------
// The page loads the copy with boxes drawn in. Here we show the plain X-ray instead and put
// each box on top as its own element, placed in % of the image size so it scales with the page.
const xrayImg = document.getElementById("xray-img");
const boxLayer = document.getElementById("xray-boxes");
if (xrayImg && boxLayer) {
  const figure = document.getElementById("xray-figure");
  const toggle = document.getElementById("show-boxes");
  const boxes = Array.from(boxLayer.querySelectorAll(".box"));
  const cards = Array.from(document.querySelectorAll(".findings li[data-index]"));

  const place = () => {
    const w = xrayImg.naturalWidth, h = xrayImg.naturalHeight;
    if (!w || !h) return;
    boxes.forEach((box) => {
      const [x1, y1, x2, y2] = box.dataset.box.split(",").map(Number);
      Object.assign(box.style, {
        left: (100 * x1 / w) + "%", top: (100 * y1 / h) + "%",
        width: (100 * (x2 - x1) / w) + "%", height: (100 * (y2 - y1) / h) + "%",
      });
      box.classList.toggle("low", y1 / h < 0.08);   // label goes under boxes at the very top
      box.hidden = false;
    });
  };
  const usePlain = () => {
    xrayImg.addEventListener("load", place, { once: true });
    xrayImg.src = xrayImg.dataset.original;
  };
  if (boxes.length) {
    if (xrayImg.complete && xrayImg.naturalWidth) usePlain();
    else xrayImg.addEventListener("load", usePlain, { once: true });
  }

  // Point at a box or a finding and both light up
  const light = (index, on) => {
    boxes.concat(cards).forEach((el) => { if (el.dataset.index === index) el.classList.toggle("lit", on); });
  };
  boxes.concat(cards).forEach((el) => {
    el.addEventListener("mouseenter", () => light(el.dataset.index, true));
    el.addEventListener("mouseleave", () => light(el.dataset.index, false));
  });
  boxes.forEach((box) => box.addEventListener("click", (e) => {
    e.stopPropagation();                                // don't open the zoom viewer
    const card = document.getElementById("finding-" + box.dataset.index);
    if (card) { card.scrollIntoView({ behavior: "smooth", block: "center" }); light(box.dataset.index, true);
                setTimeout(() => light(box.dataset.index, false), 1600); }
  }));

  if (toggle) toggle.addEventListener("change", () => {
    if (boxes.length) figure.classList.toggle("boxes-off", !toggle.checked);
    else xrayImg.src = toggle.checked ? xrayImg.dataset.annotated : xrayImg.dataset.original;
  });
}

// ---------- 5. Drag-and-drop upload with a preview ----------
document.querySelectorAll("[data-dropzone]").forEach((zone) => {
  const input = zone.querySelector("input[type=file]");
  const name = zone.querySelector("[data-drop-name]");
  const preview = zone.querySelector("[data-drop-preview]");
  const icon = zone.querySelector(".icon");
  const show = () => {
    const file = input.files[0];
    if (!file) return;
    zone.classList.add("has-file");
    name.textContent = file.name;
    if (file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = () => { preview.src = reader.result; preview.hidden = false; icon.hidden = true; };
      reader.readAsDataURL(file);
    }
  };
  input.addEventListener("change", show);
  ["dragenter", "dragover"].forEach((type) => zone.addEventListener(type, (e) => { e.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((type) => zone.addEventListener(type, () => zone.classList.remove("over")));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; show(); }
  });
});

// ---------- 6. Loading page while the AI reads the X-ray ----------
// The analysis runs on the server before the results page loads, so for those few seconds
// we show what SmartDent is doing. The step timings are approximate.
const analysing = document.getElementById("analysing");
if (analysing) {
  const steps = Array.from(analysing.querySelectorAll(".steps li"));
  const timer = analysing.querySelector("[data-timer]");
  const previewImg = analysing.querySelector("[data-preview]");
  const ghost = analysing.querySelector(".ghost");
  const startAt = [0, 1.2, 2.6, 6.5];          // seconds after sending
  let clock = null;

  const start = (previewSrc) => {
    if (previewSrc) { previewImg.src = previewSrc; previewImg.hidden = false; if (ghost) ghost.hidden = true; }
    analysing.hidden = false;
    document.body.style.overflow = "hidden";
    const t0 = performance.now();
    clock = setInterval(() => {
      const s = (performance.now() - t0) / 1000;
      timer.textContent = s.toFixed(1) + " s";
      const now = startAt.filter((t) => s >= t).length - 1;
      steps.forEach((li, i) => { li.classList.toggle("done", i < now); li.classList.toggle("now", i === now); });
    }, 100);
  };
  const stop = () => {
    clearInterval(clock);
    analysing.hidden = true;
    document.body.style.overflow = "";
  };

  document.querySelectorAll("form[data-analyse]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (e.defaultPrevented) return;                     // e.g. a confirm() was cancelled
      const file = form.querySelector("input[type=file]");
      if (file && !file.files.length) return;             // nothing chosen: let the server show the error
      const shown = form.closest(".upload-card") && form.querySelector("[data-drop-preview]:not([hidden])");
      start(shown ? shown.src : null);
    });
  });
  // Coming back with the Back button can show the old page from memory: hide the overlay again.
  window.addEventListener("pageshow", stop);
}

// ---------- 7. Mark a finding the AI missed: drag a box on the X-ray, pick the condition, save ----------
// The box is saved in pixels of the original image (like the AI's boxes), so it lines up at any page size.
const drawButton = document.getElementById("start-drawing");
const addForm = document.getElementById("add-finding-form");
if (drawButton && addForm && xrayImg && boxLayer) {
  const figure = document.getElementById("xray-figure");
  const toggle = document.getElementById("show-boxes");
  const hint = addForm.querySelector("[data-draw-hint]");
  const save = addForm.querySelector("button[type=submit]");
  const coords = ["x1", "y1", "x2", "y2"].map((name) => addForm.elements[name]);
  const condition = addForm.elements["label"];
  const colours = JSON.parse(addForm.dataset.colours || "{}");
  const draft = document.createElement("i");
  draft.className = "box draft";
  draft.hidden = true;
  boxLayer.appendChild(draft);
  let start = null;

  const colour = () => draft.style.setProperty("--c", colours[condition.value] || "#62D9FF");
  const fraction = (e) => {                     // pointer position as 0..1 of the picture
    const r = boxLayer.getBoundingClientRect();
    const clamp = (v) => Math.min(1, Math.max(0, v));
    return [clamp((e.clientX - r.left) / r.width), clamp((e.clientY - r.top) / r.height)];
  };
  const show = (a, b) => {
    Object.assign(draft.style, {
      left: 100 * Math.min(a[0], b[0]) + "%", top: 100 * Math.min(a[1], b[1]) + "%",
      width: 100 * Math.abs(a[0] - b[0]) + "%", height: 100 * Math.abs(a[1] - b[1]) + "%",
    });
  };
  const open = () => {
    addForm.hidden = false;
    drawButton.hidden = true;
    figure.classList.add("drawing");
    figure.classList.remove("boxes-off");
    if (toggle) toggle.checked = true;
    colour();
    figure.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  const close = () => {
    addForm.hidden = true;
    drawButton.hidden = false;
    figure.classList.remove("drawing");
    draft.hidden = true;
    coords.forEach((input) => { input.value = ""; });
    save.disabled = true;
    hint.textContent = "Drag on the X-ray to draw a box around the area.";
  };

  drawButton.hidden = false;
  drawButton.addEventListener("click", open);
  addForm.querySelector("[data-cancel]").addEventListener("click", close);
  condition.addEventListener("change", colour);

  boxLayer.addEventListener("pointerdown", (e) => {
    if (!figure.classList.contains("drawing")) return;
    e.preventDefault();
    boxLayer.setPointerCapture(e.pointerId);
    start = fraction(e);
    show(start, start);
    draft.hidden = false;
  });
  boxLayer.addEventListener("pointermove", (e) => { if (start) show(start, fraction(e)); });
  boxLayer.addEventListener("pointerup", (e) => {
    if (!start) return;
    const end = fraction(e);
    const w = xrayImg.naturalWidth, h = xrayImg.naturalHeight;
    const box = [Math.min(start[0], end[0]) * w, Math.min(start[1], end[1]) * h,
                 Math.max(start[0], end[0]) * w, Math.max(start[1], end[1]) * h].map(Math.round);
    start = null;
    const bigEnough = box[2] - box[0] >= 4 && box[3] - box[1] >= 4;
    coords.forEach((input, i) => { input.value = bigEnough ? box[i] : ""; });
    save.disabled = !bigEnough;
    draft.hidden = !bigEnough;
    hint.textContent = bigEnough
      ? "Box drawn. Pick what it is and save. Drag again to redraw it."
      : "That box is too small. Drag across the area on the X-ray.";
  });
  boxLayer.addEventListener("pointercancel", () => { start = null; });
}
