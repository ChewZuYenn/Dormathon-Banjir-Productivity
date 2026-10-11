import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const canvas = document.querySelector("#office-canvas");
const stage = document.querySelector(".office-stage");
const loading = document.querySelector("#loading");
const renderStatus = document.querySelector("#render-status");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
} catch (error) {
  showError("Your browser could not start WebGL. Use Chrome, Edge or Safari with hardware acceleration on.", error);
}

function showError(message, error) {
  loading.classList.add("error");
  loading.querySelector("strong").textContent = "The office failed to load";
  document.querySelector("#loading-detail").textContent = message;
  renderStatus.textContent = "Load failed";
  if (error) console.error(error);
}

if (renderer) init(renderer);

function init(renderer) {
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.02;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-7, 7, 4, -4, 0.05, 100);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = !reducedMotion;
  controls.dampingFactor = 0.09;
  controls.enablePan = true;
  controls.screenSpacePanning = true;
  controls.minPolarAngle = Math.PI * 0.08;
  controls.maxPolarAngle = Math.PI * 0.48;
  controls.minZoom = 0.55;
  controls.maxZoom = 3.2;
  controls.autoRotateSpeed = 0.65;
  controls.rotateSpeed = 0.60;
  controls.panSpeed = 0.60;
  controls.zoomSpeed = 0.80;
  controls.touches.ONE = THREE.TOUCH.ROTATE;
  controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
  const ambient = new THREE.HemisphereLight(0xfff8e9, 0x979975, 1.7);
  scene.add(ambient);
  const sun = new THREE.DirectionalLight(0xffedd0, 2.4);
  sun.position.set(-4, 8, 5);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -6;
  sun.shadow.camera.right = 6;
  sun.shadow.camera.top = 6;
  sun.shadow.camera.bottom = -6;
  sun.shadow.camera.near = 0.1;
  sun.shadow.camera.far = 24;
  sun.shadow.normalBias = 0.025;
  sun.shadow.bias = -0.0001;
  sun.shadow.radius = 3;
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0xe7efff, 0.75);
  fill.position.set(6, 5, -4);
  scene.add(fill);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.ShadowMaterial({ color: 0x4b5f3f, opacity: 0.10 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.33;
  ground.receiveShadow = true;
  scene.add(ground);

  let model = null;
  let ready = false;
  const center = new THREE.Vector3(0, 1.4, 0);
  let verticalSize = 10.0;
  let meshCount = 0;
  const homeDirection = new THREE.Vector3(0.56, 0.72, 0.80).normalize();

  function resize() {
    const width = stage.clientWidth;
    const height = stage.clientHeight;
    renderer.setSize(width, height, false);
    const aspect = width / height;
    const heightForWidth = 11.6 / aspect;
    const viewHeight = Math.max(verticalSize, heightForWidth);
    camera.left = -viewHeight * aspect / 2;
    camera.right = viewHeight * aspect / 2;
    camera.top = viewHeight / 2;
    camera.bottom = -viewHeight / 2;
    camera.updateProjectionMatrix();
  }
  function resetView() {
    controls.autoRotate = false;
    document.querySelector("#rotate-toggle").setAttribute("aria-pressed", "false");
    document.querySelector("#rotate-toggle").textContent = "Auto-rotate";
    // Drain accumulated rotate/pan inertia before assigning the exact home view.
    // A non-damped update consumes and clears these deltas through the public API.
    const damping = controls.enableDamping;
    controls.enableDamping = false;
    controls.update(0);
    camera.zoom = 1;
    camera.position.copy(center).addScaledVector(homeDirection, 14);
    camera.lookAt(center);
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
    const shiftedCenter = center.clone().addScaledVector(up, -0.68);
    camera.position.addScaledVector(up, -0.68);
    controls.target.copy(shiftedCenter);
    camera.updateProjectionMatrix();
    controls.update(0);
    controls.saveState();
    controls.enableDamping = damping;
  }
  resize();
  resetView();
  new ResizeObserver(resize).observe(stage);
  canvas.addEventListener("contextmenu", event => event.preventDefault());
  canvas.addEventListener("pointerdown", () => canvas.focus({ preventScroll: true }));
  document.querySelector("#reset-view").addEventListener("click", resetView);
  document.querySelector("#rotate-toggle").addEventListener("click", event => {
    controls.autoRotate = !controls.autoRotate;
    event.currentTarget.setAttribute("aria-pressed", String(controls.autoRotate));
    event.currentTarget.textContent = controls.autoRotate ? "Stop rotating" : "Auto-rotate";
  });
  function changeZoom(factor) {
    camera.zoom = THREE.MathUtils.clamp(camera.zoom * factor, controls.minZoom, controls.maxZoom);
    camera.updateProjectionMatrix();
  }
  document.querySelector("#zoom-in").addEventListener("click", () => changeZoom(1.15));
  document.querySelector("#zoom-out").addEventListener("click", () => changeZoom(1 / 1.15));
  canvas.addEventListener("keydown", event => {
    if (["+", "=", "-", "r", "R"].includes(event.key)) {
      event.preventDefault();
      if (event.key.toLowerCase() === "r") resetView();
      else changeZoom(event.key === "-" ? 1 / 1.15 : 1.15);
    } else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      const spherical = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
      if (event.key === "ArrowLeft") spherical.theta -= 0.08;
      if (event.key === "ArrowRight") spherical.theta += 0.08;
      if (event.key === "ArrowUp") spherical.phi -= 0.08;
      if (event.key === "ArrowDown") spherical.phi += 0.08;
      spherical.phi = THREE.MathUtils.clamp(spherical.phi, controls.minPolarAngle, controls.maxPolarAngle);
      camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
      controls.update();
    }
  });

  const loader = new GLTFLoader();
  loader.load("./assets/office.glb", gltf => {
    model = gltf.scene;
    model.name = "OfficeModel";
    model.traverse(object => {
      if (!object.isMesh) return;
      meshCount++;
      object.castShadow = true;
      object.receiveShadow = true;
      // Materials and geometry are those of the delivered GLB, not replacement artwork.
    });
    scene.add(model);
    const box = new THREE.Box3().setFromObject(model);
    box.getCenter(center);
    verticalSize = 10.0;
    resize();
    resetView();
    ready = true;
    loading.classList.add("hidden");
    setTimeout(() => loading.hidden = true, 450);
    renderStatus.textContent = "WebGL · " + meshCount + " meshes";
    document.querySelector("#current-step").textContent = "Try dragging the office, or scroll to zoom in.";
  }, progress => {
    if (progress.total > 0) document.querySelector("#loading-detail").textContent = "Loading model " + Math.round(progress.loaded / progress.total * 100) + "%";
  }, error => showError("Open this page through a web server, not by double-clicking the HTML. Also check that assets/office.glb exists.", error));

  let previous = performance.now();
  renderer.setAnimationLoop(time => {
    const delta = Math.min((time - previous) / 1000, 0.10);
    previous = time;
    controls.update(delta);
    renderer.render(scene, camera);
  });
  // Read-only diagnostics used by automated interaction tests.
  window.OfficeView = Object.freeze({
    get ready() { return ready; },
    snapshot() { return { ready, meshes: meshCount, position: camera.position.toArray(), target: controls.target.toArray(), zoom: camera.zoom, autoRotate: controls.autoRotate, renderCalls: renderer.info.render.calls, width: stage.clientWidth, height: stage.clientHeight }; }
  });
}

const agents = ["Secretary", "Logistics", "Financial"];
let running = false;
const labels = { idle: "Idle", working: "Working", done: "Done", error: "Error" };
function setState(name, status, text) {
  const card = document.querySelector('[data-agent="' + name + '"]');
  card.dataset.status = status;
  card.querySelector(".status-badge").textContent = labels[status];
  card.querySelector(".agent-detail").textContent = text;
}
document.querySelector("#task-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (running) return;
  const task = document.querySelector("#task-input").value.trim();
  if (!task) { document.querySelector("#current-step").textContent = "Enter a task goal first."; return; }
  running = true;
  document.querySelector("#start-button").disabled = true;
  const step = document.querySelector("#current-step");
  const live = document.querySelector("#live-read").checked;
  agents.forEach(name => setState(name, "idle", "Queued"));
  document.querySelector("#plan").hidden = true;
  step.textContent = "“" + task + "” — running the three agents" + (live ? " (reading the scans live with Gemini)…" : "…");
  try {
    // Streamed NDJSON: one status line per agent step, then the result
    const res = await fetch("/api/run/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal: task, use_images: live }),
    });
    if (res.status === 429) {
      const limit = new Error((await res.json().catch(() => ({}))).error || "Too many runs, try again later.");
      limit.noHint = true;
      throw limit;
    }
    if (!res.ok || !res.body) throw new Error("HTTP " + res.status);
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "", data = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (value) buffer += value;
      const lines = buffer.split("\n");
      buffer = done ? "" : lines.pop();
      for (const line of lines.filter(l => l.trim())) {
        const msg = JSON.parse(line);
        if (msg.kind === "status") {
          setState(msg.agent, msg.status, msg.step);
          step.textContent = msg.agent + " · " + msg.step;
        } else if (msg.kind === "plan") renderPlan(msg.plan);
        else if (msg.kind === "result") data = msg.data;
        else if (msg.kind === "error") throw new Error(msg.error);
      }
      if (done) break;
    }
    if (!data || !data.success) throw new Error("The run ended without a result");
    setState("Secretary", "done", data.secretary.tasks.length + " tasks · " + data.secretary.chase_emails.length + " draft emails");
    const gmail = data.gmail || {};
    const gmailNote = gmail.status === "ok" ? " · Gmail " + gmail.emails.length + " emails / " + gmail.document_count + " documents" : " · Gmail not connected";
    const check = data.logistics.verification;
    const checkNote = check && check.accuracy != null ? " · " + check.fields_matched + "/" + check.fields_checked + " fields match the hand-checked set" : "";
    setState("Logistics", "done", data.logistics.count + " records" + checkNote + gmailNote);
    setState("Financial", "done", data.financial.exception_count + " exceptions");
    window.lastRun = data; // full result, for inspection in the console
    renderRun(data);
    step.textContent = "“" + task + "” done. Results below; full JSON: lastRun in the browser console.";
  } catch (error) {
    agents.forEach(name => setState(name, "error", error.message));
    step.textContent = "Run failed: " + error.message + (error.noHint ? "" : " (start with python app.py and open http://127.0.0.1:5000/web-office/)");
  } finally {
    running = false;
    document.querySelector("#start-button").disabled = false;
  }
});


// === Render a run: AI Summary, Checklist, Results (all text via textContent) ===
function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v; else if (v != null) node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null) node.append(c instanceof Node ? c : String(c));
  return node;
}
const rm = n => "RM " + Number(n || 0).toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const TYPE_LABELS = {
  conflicting_printed_values: "Conflicting printed figures",
  arithmetic_mismatch: "Totals don't add up",
  duplicate_similar_confidence: "Duplicate invoice",
  missing_po_match: "PO referenced but not on file",
  missing_po_reference_high_value: "High-value invoice without a PO",
  no_due_date: "No due date",
  low_confidence: "Low extraction confidence",
  quantity_mismatch: "Quantity differs from the PO",
  tax_rate_anomaly: "SST doesn't match the printed rate",
};
const typeLabel = t => TYPE_LABELS[t] || String(t || "other").replace(/_/g, " ");
const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 };
// Only the bundled test documents can be opened; Gmail refs have no public file
const docLink = ref => typeof ref === "string" && ref.startsWith("test-documents/")
  ? el("a", { href: "/api/documents/" + ref, target: "_blank", rel: "noopener" }, "view")
  : el("span", { class: "muted" }, ref ? "—" : "");

function renderRun(data) {
  const exceptions = (data.financial.exceptions && data.financial.exceptions.exceptions) || [];
  // Patterns that hit many documents (no due date, PO not on file) are one checklist line each, not one per document
  const observations = data.secretary.observations || [];
  const systemic = new Set(observations.map(o => o.type));
  const checklist = exceptions.filter(e => !systemic.has(e.type)).concat(observations.map(o =>
    ({ type: o.type, severity: "info", reason: o.documents.join(", "), suggested_action: o.text, source_ref: "observation" })));
  renderPlan(data.plan, data.sources);
  renderSummary(data, exceptions);
  renderChecklist(checklist);
  renderResults(data, exceptions);
}

const SOURCE_LABELS = { llm: "Gemini", hand_checked: "hand-checked records", python_engine: "deterministic engine",
  python_fallback: "rule-based fallback (no LLM)", static_fallback: "fixed fallback plan", python_task_generator: "rules" };
const PHASE_STATUS = { pending: ["Pending", "pending"], in_progress: ["Working", "warning"], done: ["Done", "info"] };
const sourceLabel = s => SOURCE_LABELS[s] || s || "?";
function renderPlan(plan, sources) {
  const phases = (plan && plan.phases) || [];
  if (!phases.length) return;
  document.querySelector("#plan-source").textContent = "written by the Secretary · " + sourceLabel(plan.source);
  document.querySelector("#plan-phases").replaceChildren(...phases.map(p => {
    const [label, cls] = PHASE_STATUS[p.status] || [p.status, "pending"];
    return el("li", null, el("span", { class: "sev sev-" + cls }, label), " ", el("strong", null, p.agent), " — " + (p.action || ""));
  }));
  if (sources) document.querySelector("#plan-sources").textContent = "Plan: " + sourceLabel(sources.plan) +
    " · Extraction: " + sourceLabel(sources.logistics) + " · Ledger & checks: " + sourceLabel(sources.financial) +
    " · Tasks: " + sourceLabel(sources.tasks) + " · Emails & top actions: " + sourceLabel(sources.secretary);
  document.querySelector("#plan").hidden = false;
}

function renderSummary(data, exceptions) {
  const groups = {};
  for (const e of exceptions) (groups[e.type] = groups[e.type] || []).push(e);
  const ordered = Object.values(groups).sort((a, b) =>
    (SEVERITY_ORDER[a[0].severity] ?? 3) - (SEVERITY_ORDER[b[0].severity] ?? 3) || b.length - a.length);
  document.querySelector("#wrong-list").replaceChildren(...ordered.map(list => {
    const docs = [...new Set(list.map(e => e.document_number).filter(Boolean))];
    return el("li", null, el("strong", null, list.length + " × " + typeLabel(list[0].type)),
      " — " + (list[0].reason || "") + (docs.length > 1 ? " (" + docs.slice(0, 4).join(", ") + (docs.length > 4 ? ", …" : "") + ")" : ""));
  }));
  const report = data.secretary.final_report || {};
  const risk = report.at_risk || { total: 0, items: [] };
  const headline = document.querySelector("#ai-headline");
  headline.replaceChildren(
    el("strong", null, rm(risk.total) + " at risk"),
    el("p", null, risk.items.map(i => i.document_number + " " + rm(i.amount) + " (" + i.reason + ")").join(" · ") || "No duplicate or mis-added totals found."),
    report.cash_in ? null : el("p", null, "Payables close: all " + data.logistics.count + " documents are purchases, so cash in is RM 0.00."));
  headline.hidden = false;
  const actions = report.top_3_actions || [];
  document.querySelector("#change-list").replaceChildren(...actions.map(a => el("li", null, a)));
  document.querySelector("#ai-generated").textContent =
    "Built by the agents · " + new Date().toLocaleTimeString() + " · secretary: " + (data.sources.secretary || "?");
}

// Checklist = one item per exception, grouped by the same severity as the AI Summary
function renderChecklist(exceptions) {
  const KEY = "banjir-checklist-state";
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
  const groups = [
    { title: "🔴 Critical — fix first", cls: "critical", match: s => s === "critical" },
    { title: "🟡 Warnings", cls: "warning", match: s => s === "warning" },
    { title: "🟢 Info", cls: "tidy", match: s => s !== "critical" && s !== "warning" },
  ];
  const boxes = [];
  const sections = groups.map(g => {
    const items = exceptions.filter(x => g.match(x.severity));
    if (!items.length) return null;
    return el("div", { class: "check-group" }, el("h3", { class: "check-group-title " + g.cls }, g.title + " (" + items.length + ")"),
      items.map(x => {
        const id = [x.source_ref, x.type, x.document_number, x.reason].join("|");
        const box = el("input", { type: "checkbox" });
        const label = el("label", { class: "check-item", title: x.reason || "" }, box,
          " " + (x.document_number ? x.document_number + ": " : "") + (x.suggested_action || typeLabel(x.type)));
        box.checked = !!saved[id];
        label.classList.toggle("checked", box.checked);
        box.addEventListener("change", () => {
          label.classList.toggle("checked", box.checked);
          saved[id] = box.checked;
          try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {}
          progress();
        });
        boxes.push(box);
        return label;
      }));
  });
  document.querySelector("#check-groups").replaceChildren(...sections.filter(Boolean));
  function progress() {
    const done = boxes.filter(b => b.checked).length;
    const pct = boxes.length ? Math.round(done / boxes.length * 100) : 0;
    document.querySelector("#check-progress-fill").style.width = pct + "%";
    document.querySelector("#check-progress-text").textContent = done + " / " + boxes.length + " fixed (" + pct + "%)";
  }
  progress();
}
function table(headers, rows) {
  return el("div", { class: "table-wrap" }, el("table", null,
    el("thead", null, el("tr", null, headers.map(h => el("th", null, h)))),
    el("tbody", null, rows.map(r => el("tr", null, r.map(c => el("td", null, c)))))));
}

// AutoCount AP invoice import layout: one row per ledger line, document fields repeated on each line.
// CreditorCode is left blank and AccNo carries our category code: both must be mapped to the codes in the
// AutoCount company during import. DocType and SourceRef are extra columns for traceability.
const AUTOCOUNT_COLUMNS = ["DocNo", "DocDate", "CreditorCode", "CreditorName", "SupplierInvoiceNo", "Description",
  "AccNo", "DetailDescription", "Qty", "UnitPrice", "Amount", "TaxCode", "TaxAmt", "CurrencyCode", "DocType", "SourceRef"];
function csvCell(v) {
  let s = v == null ? "" : String(v);
  if (typeof v === "string" && /^[=+\-@]/.test(s)) s = "'" + s; // keep spreadsheet formulas from running
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
function autoCountCsv(data) {
  // The duplicate copy of an invoice is left out, as in the ledger totals, so it isn't booked twice
  const rows = ((data.financial.ledger || {}).rows || []).filter(r => !(r.flags || []).includes("duplicate"));
  const lines = rows.map(r => [r.document_number, r.document_date, "", r.vendor_name, r.document_number,
    (r.document_type === "receipt" ? "Cash purchase " : "Purchase invoice ") + r.document_number,
    r.category, r.description, r.quantity, r.unit_price, Number(r.amount || 0).toFixed(2),
    r.tax_amount ? "SST" : "", Number(r.tax_amount || 0).toFixed(2), "MYR",
    r.document_type === "receipt" ? "Cash Purchase" : "AP Invoice", r.source_ref]);
  return "﻿" + [AUTOCOUNT_COLUMNS, ...lines].map(l => l.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
function exportAutoCount(data) {
  const csv = autoCountCsv(data);
  const a = el("a", { href: URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" })),
    download: "autocount-ap-" + new Date().toISOString().slice(0, 10) + ".csv" });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function renderResults(data, exceptions) {
  const report = data.secretary.final_report || {};
  const ledger = data.financial.ledger || {};
  const views = {
    report: () => el("div", null,
      report.cash_in ? null : el("h4", null, "Payables close"),
      report.cash_in ? null : el("p", { class: "muted" }, "All " + data.logistics.count +
        " documents are purchases (invoices, receipts, purchase orders); there are no sales documents, so cash in is RM 0.00."),
      el("div", { class: "stat-grid" }, [
        [report.cash_in ? "Cash in" : "Cash in (no sales documents)", rm(report.cash_in)],
        ["At risk", rm((report.at_risk || {}).total)], ["Cash out (incl. SST)", rm(report.cash_out)], ["Net cash", rm(report.net_cash)],
        ["SST", rm(report.total_tax)], ["Reconciled invoices", Math.round((report.reconciliation_rate || 0) * 100) + "%"],
        ["Exceptions", report.total_exceptions], ["Tasks", report.tasks_generated], ["Chase emails", report.chase_emails_drafted],
      ].map(([k, v]) => el("div", { class: "stat" }, el("span", null, k), el("strong", null, v)))),
      el("p", { class: "muted" }, "Every figure comes from the Financial ledger (" + (ledger.rows || []).length + " rows), not from the language model."),
      data.logistics.verification ? el("p", { class: "muted" }, "Live extraction check: Gemini read " + data.logistics.verification.documents_compared + " scans; " + data.logistics.verification.fields_matched + " of " + data.logistics.verification.fields_checked + " key fields match the hand-checked records" + (data.logistics.verification.mismatches.length ? " (mismatches: " + data.logistics.verification.mismatches.map(m => m.source_ref.split("/").pop() + " " + m.field).join(", ") + ")." : ".")) : null,
      el("h4", null, "Top actions"), el("ol", null, (report.top_3_actions || []).map(a => el("li", null, a))),
      (report.observations || []).length ? el("h4", null, "Patterns across the documents") : null,
      el("ul", null, (report.observations || []).map(o => el("li", null, o))),
      el("h4", null, "By category (excl. SST)"),
      table(["Category", "Rows", "Total"], (report.categories || []).map(c => [c.category, c.count, rm(c.total)]))),
    exceptions: () => table(["Severity", "Problem", "Document", "Vendor", "Reason", "Source"],
      [...exceptions].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3))
        .map(e => [el("span", { class: "sev sev-" + e.severity }, e.severity), typeLabel(e.type), e.document_number || "",
          e.vendor_name || "", e.reason || "", docLink(e.source_ref)])),
    tasks: () => table(["Priority", "Task", "Action required"],
      (data.secretary.tasks || []).map(t => ["P" + t.priority, t.title, t.action_required || ""])),
    emails: () => {
      const emails = data.secretary.chase_emails || [];
      if (!emails.length) return el("p", { class: "muted" }, "No vendor documents need a chase email.");
      return el("div", { class: "email-list" }, emails.map(m => el("article", { class: "email" },
        el("div", { class: "email-meta" }, el("span", { class: "sev sev-info" }, "Draft · not sent"),
          " To " + (m.vendor_name || "vendor") + " · " + (m.related_invoice || "") + " · written by " + (m.source === "llm" ? "Gemini" : "template") + " · ",
          docLink(m.source_ref)),
        el("h4", null, m.subject || ""), el("pre", null, m.body || ""))));
    },
    ledger: () => table(["Row", "Date", "Document", "Vendor", "Description", "Category", "Amount", "SST", "Source"],
      (ledger.rows || []).map(r => [r.row_id, r.document_date || "", r.document_number || "", r.vendor_name || "",
        r.description || "", r.category, rm(r.amount), rm(r.tax_amount), docLink(r.source_ref)])),
  };
  const body = document.querySelector("#results-body");
  const tabs = document.querySelectorAll(".results-tabs [data-tab]");
  const show = name => {
    tabs.forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    body.replaceChildren(views[name]());
  };
  tabs.forEach(b => { b.onclick = () => show(b.dataset.tab); });
  document.querySelector("#export-autocount").onclick = () => exportAutoCount(data);
  document.querySelector("#results").hidden = false;
  show("report");
}