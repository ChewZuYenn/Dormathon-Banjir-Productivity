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
  // ponytail: /api/run is synchronous, so all cards work at once; add job polling for per-agent progress
  agents.forEach(name => setState(name, "working", "Running…"));
  step.textContent = "“" + task + "” — running the three agents…";
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal: task }),
    });
    const data = await res.json().catch(() => ({ error: "HTTP " + res.status }));
    if (!res.ok || !data.success) throw new Error(data.error || "HTTP " + res.status);
    setState("Secretary", "done", data.secretary.tasks.length + " tasks · " + data.secretary.chase_emails.length + " draft emails");
    const gmail = data.gmail || {};
    const gmailNote = gmail.status === "ok" ? " · Gmail " + gmail.emails.length + " emails / " + gmail.document_count + " documents" : " · Gmail not connected";
    setState("Logistics", "done", data.logistics.count + " records" + gmailNote);
    setState("Financial", "done", data.financial.exception_count + " exceptions");
    window.lastRun = data; // full result, for inspection in the console
    step.textContent = "“" + task + "” done. Full result: lastRun in the browser console.";
  } catch (error) {
    agents.forEach(name => setState(name, "error", error.message));
    step.textContent = "Run failed: " + error.message + " (start with python app.py and open http://127.0.0.1:5000/web-office/)";
  } finally {
    running = false;
    document.querySelector("#start-button").disabled = false;
  }
});

// === Interactive checklist checkboxes — persist to localStorage ===
(function() {
  const CHECK_KEY = "banjir-checklist-state";
  const totalChecks = document.querySelectorAll('.check-item input[type="checkbox"][data-check]').length;

  // Load saved state
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(CHECK_KEY) || "{}"); } catch(e) {}

  document.querySelectorAll('.check-item input[type="checkbox"][data-check]').forEach(cb => {
    const id = cb.getAttribute("data-check");
    if (saved[id]) {
      cb.checked = true;
      cb.closest(".check-item").classList.add("checked");
    }
    cb.addEventListener("change", () => {
      if (cb.checked) cb.closest(".check-item").classList.add("checked");
      else cb.closest(".check-item").classList.remove("checked");
      saved[id] = cb.checked;
      try { localStorage.setItem(CHECK_KEY, JSON.stringify(saved)); } catch(e) {}
      updateProgress();
    });
  });

  function updateProgress() {
    const checked = document.querySelectorAll('.check-item input[type="checkbox"]:checked').length;
    const pct = totalChecks > 0 ? Math.round(checked / totalChecks * 100) : 0;
    const fill = document.getElementById("check-progress-fill");
    const text = document.getElementById("check-progress-text");
    if (fill) fill.style.width = pct + "%";
    if (text) text.textContent = checked + " / " + totalChecks + " fixed (" + pct + "%)";
  }
  updateProgress();
})();
