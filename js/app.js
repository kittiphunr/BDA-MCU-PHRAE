/* ทัวร์ 360° หอพุทธศิลป์ — ผูกภาพ 360° เข้าด้วยกันแบบ Street View */
(function () {
  "use strict";

  var TOUR = window.TOUR;
  var ARROW_PITCH = -24; // ลูกศรวางบนพื้น
  var FORWARD_CONE = 50; // องศาที่ถือว่า "อยู่ข้างหน้า" สำหรับปุ่มเดินหน้า
  var EDIT = /[?&]edit=1/.test(location.search);
  var SVG_NS = "http://www.w3.org/2000/svg";

  var $ = function (id) { return document.getElementById(id); };
  var byId = {};
  TOUR.scenes.forEach(function (s) { byId[s.id] = s; });

  /* ---------- คำนวณทิศ ---------- */

  function norm(deg) {
    deg = ((deg + 180) % 360 + 360) % 360 - 180;
    return deg === -180 ? 180 : deg;
  }

  // ทิศบนแผนผัง (0° = ด้านบนของแผนผัง, หมุนตามเข็มนาฬิกา)
  function mapBearing(from, to) {
    if (!from.map || !to.map) return null;
    return Math.atan2(to.map.x - from.map.x, -(to.map.y - from.map.y)) * 180 / Math.PI;
  }

  // แปลงทิศบนแผนผังเป็น yaw ในภาพของ scene และกลับกัน
  function bearingToYaw(scene, bearing) { return norm(bearing + (scene.northOffset || 0)); }
  function yawToBearing(scene, yaw) { return norm(yaw - (scene.northOffset || 0)); }

  /* ---------- สร้างกราฟการเชื่อมต่อ (ลิงก์สองทาง) ---------- */

  var edges = {}; // edges[from][to] = { yaw, pitch }
  TOUR.scenes.forEach(function (s) { edges[s.id] = {}; });

  TOUR.scenes.forEach(function (s) {
    (s.links || []).forEach(function (l) {
      if (!byId[l.to]) { console.warn("ไม่พบจุด", l.to, "ที่ลิงก์จาก", s.id); return; }
      edges[s.id][l.to] = Object.assign({}, edges[s.id][l.to], l);
      if (!l.oneWay && !edges[l.to][s.id]) edges[l.to][s.id] = { to: s.id, auto: true };
    });
  });

  function linkHotspot(from, link) {
    var to = byId[link.to];
    var bearing = mapBearing(from, to);
    var yaw = link.yaw != null ? link.yaw : bearing != null ? bearingToYaw(from, bearing) : 0;
    if (bearing == null) bearing = yawToBearing(from, yaw);
    return {
      type: "scene",
      sceneId: to.id,
      yaw: yaw,
      pitch: link.pitch != null ? link.pitch : ARROW_PITCH,
      // หันหน้าไปทิศเดียวกับที่เดินมา (เหมือน Street View)
      targetYaw: link.targetYaw != null ? link.targetYaw : bearingToYaw(to, bearing),
      targetPitch: 0,
      cssClass: "sv-arrow",
      createTooltipFunc: renderArrow,
      createTooltipArgs: to.title
    };
  }

  function renderArrow(div, title) {
    div.innerHTML =
      '<span class="sv-arrow-shape" aria-hidden="true"></span>' +
      '<span class="sv-arrow-label"></span>';
    div.querySelector(".sv-arrow-label").textContent = title;
    div.setAttribute("role", "button");
    div.setAttribute("aria-label", "ไปยัง " + title);
  }

  function infoHotspot(info) {
    return {
      type: "info",
      yaw: info.yaw,
      pitch: info.pitch || 0,
      cssClass: "sv-info",
      createTooltipFunc: function (div) {
        div.innerHTML = '<span class="sv-info-dot">i</span><span class="sv-info-label"></span>';
        div.querySelector(".sv-info-label").textContent = info.title;
        div.setAttribute("role", "button");
        div.setAttribute("aria-label", info.title);
      },
      clickHandlerFunc: function () { showInfo(info); }
    };
  }

  /* ---------- ตั้งค่า Pannellum ---------- */

  var scenesCfg = {};
  TOUR.scenes.forEach(function (s) {
    var hs = [];
    Object.keys(edges[s.id]).forEach(function (to) { hs.push(linkHotspot(s, edges[s.id][to])); });
    (s.infos || []).forEach(function (i) { hs.push(infoHotspot(i)); });
    scenesCfg[s.id] = {
      type: "equirectangular",
      panorama: s.image,
      yaw: s.yaw || 0,
      pitch: s.pitch || 0,
      hotSpots: hs
    };
  });

  var startId = decodeURIComponent(location.hash.slice(1));
  if (!byId[startId]) startId = TOUR.firstScene || TOUR.scenes[0].id;

  var viewer = pannellum.viewer("viewer", {
    default: {
      firstScene: startId,
      sceneFadeDuration: 900,
      autoLoad: true,
      hfov: 100,
      minHfov: 40,
      maxHfov: 120,
      showControls: false,
      keyboardZoom: true,
      friction: 0.2,
      strings: {
        loadingLabel: "กำลังโหลดภาพ 360°...",
        loadButtonLabel: "คลิกเพื่อโหลด",
        bylineLabel: "",
        noPanoramaError: "ไม่พบภาพ 360°",
        fileAccessError: "ไม่สามารถเปิดไฟล์ %s ได้ (ให้เปิดผ่านเว็บเซิร์ฟเวอร์ ไม่ใช่ file://)",
        malformedURLError: "ที่อยู่ภาพไม่ถูกต้อง",
        iOS8WebGLError: "อุปกรณ์ไม่รองรับ WebGL",
        genericWebGLError: "เบราว์เซอร์ไม่รองรับ WebGL",
        textureSizeError: "ภาพใหญ่เกินไปสำหรับอุปกรณ์นี้ (กว้าง %s px, รองรับสูงสุด %s px)",
        unknownError: "เกิดข้อผิดพลาด"
      }
    },
    scenes: scenesCfg
  });

  /* ---------- UI ---------- */

  function currentScene() { return byId[viewer.getScene()]; }

  function updateSceneUI() {
    var s = currentScene();
    if (!s) return;
    $("scene-title").textContent = s.title;
    $("scene-desc").textContent = s.description || "";
    document.title = s.title + " · " + TOUR.title;
    if (location.hash.slice(1) !== s.id) history.replaceState(null, "", "#" + encodeURIComponent(s.id));
    Array.prototype.forEach.call(document.querySelectorAll("#scene-items button"), function (b) {
      b.classList.toggle("active", b.dataset.id === s.id);
      b.setAttribute("aria-current", b.dataset.id === s.id ? "true" : "false");
    });
    hideInfo();
    drawMap();
  }

  function goTo(id) {
    var s = currentScene();
    var target = byId[id];
    if (!target || (s && s.id === id)) return;
    var edge = s && edges[s.id][id];
    if (edge) {
      var hs = linkHotspot(s, edge);
      viewer.loadScene(id, 0, hs.targetYaw);
    } else {
      viewer.loadScene(id);
    }
  }

  // หาลิงก์ที่อยู่ใกล้ทิศที่กำลังมองที่สุด
  function forwardLink() {
    var s = currentScene();
    if (!s) return null;
    var yaw = viewer.getYaw();
    var best = null;
    Object.keys(edges[s.id]).forEach(function (to) {
      var d = Math.abs(norm(linkHotspot(s, edges[s.id][to]).yaw - yaw));
      if (d <= FORWARD_CONE && (!best || d < best.d)) best = { to: to, d: d };
    });
    return best && best.to;
  }

  function updateForwardButton() {
    var to = forwardLink();
    var btn = $("btn-forward");
    btn.disabled = !to;
    btn.textContent = to ? "เดินหน้า ▲ " + byId[to].title : "หันไปทางลูกศรเพื่อเดิน";
  }

  $("btn-forward").addEventListener("click", function () {
    var to = forwardLink();
    if (to) goTo(to);
  });

  document.addEventListener("keydown", function (e) {
    if (e.target.closest && e.target.closest("input, textarea")) return;
    if (e.key === "w" || e.key === "W" || e.key === "ไ") {
      var to = forwardLink();
      if (to) goTo(to);
    } else if (e.key === "Escape") {
      hideInfo();
    }
  });

  /* รายการจุดชม */
  var list = $("scene-items");
  TOUR.scenes.forEach(function (s, i) {
    var li = document.createElement("li");
    var b = document.createElement("button");
    b.dataset.id = s.id;
    b.innerHTML = '<span class="num"></span><span class="t"></span>';
    b.querySelector(".num").textContent = i + 1;
    b.querySelector(".t").textContent = s.title;
    b.addEventListener("click", function () {
      goTo(s.id);
      if (window.matchMedia("(max-width: 720px)").matches) togglePanel("scene-list", false);
    });
    li.appendChild(b);
    list.appendChild(li);
  });

  /* กล่องข้อมูล */
  function showInfo(info) {
    $("info-title").textContent = info.title;
    $("info-text").textContent = info.text || "";
    $("info-card").hidden = false;
  }
  function hideInfo() { $("info-card").hidden = true; }

  /* แผง */
  function togglePanel(id, show) {
    var el = $(id);
    el.hidden = show == null ? !el.hidden : !show;
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-close]"), function (b) {
    b.addEventListener("click", function () { togglePanel(b.dataset.close, false); });
  });
  $("btn-list").addEventListener("click", function () { togglePanel("scene-list"); });
  $("btn-map").addEventListener("click", function () { togglePanel("minimap"); });
  if (window.matchMedia("(max-width: 720px)").matches) togglePanel("minimap", false);

  var rotating = false;
  $("btn-rotate").addEventListener("click", function () {
    rotating = !rotating;
    if (rotating) viewer.startAutoRotate(-3); else viewer.stopAutoRotate();
    this.classList.toggle("on", rotating);
  });
  viewer.on("mousedown", function () {
    if (rotating) { rotating = false; $("btn-rotate").classList.remove("on"); }
  });

  $("btn-full").addEventListener("click", function () { viewer.toggleFullscreen(); });

  $("btn-share").addEventListener("click", function () {
    var url = location.href.split("#")[0] + "#" + encodeURIComponent(viewer.getScene());
    var done = function () { toast("คัดลอกลิงก์แล้ว"); };
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, function () { prompt("ลิงก์", url); });
    else prompt("ลิงก์", url);
  });

  var toastTimer;
  function toast(msg) {
    var t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove("show"); }, 1800);
  }

  window.addEventListener("hashchange", function () {
    var id = decodeURIComponent(location.hash.slice(1));
    if (byId[id]) goTo(id);
  });

  /* ---------- แผนผัง ---------- */

  var svg = $("map-svg");
  var cone;

  function el(name, attrs, parent) {
    var n = document.createElementNS(SVG_NS, name);
    Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(n);
    return n;
  }

  function drawMap() {
    var cur = viewer.getScene();
    svg.innerHTML = "";
    var fp = TOUR.floorPlan || {};
    if (fp.image) {
      el("image", { href: fp.image, x: 0, y: 0, width: 100, height: 100, preserveAspectRatio: "none", opacity: 0.85 }, svg);
    }
    (fp.rooms || []).forEach(function (r) {
      el("rect", { x: r.x, y: r.y, width: r.w, height: r.h, rx: 1.5, class: "room" }, svg);
      var t = el("text", { x: r.x + r.w / 2, y: r.y + 4.2, class: "room-label" }, svg);
      t.textContent = r.label;
    });
    // เส้นทางเดิน
    var drawn = {};
    TOUR.scenes.forEach(function (s) {
      Object.keys(edges[s.id]).forEach(function (to) {
        var key = [s.id, to].sort().join("|");
        if (drawn[key] || !s.map || !byId[to].map) return;
        drawn[key] = true;
        el("line", { x1: s.map.x, y1: s.map.y, x2: byId[to].map.x, y2: byId[to].map.y, class: "path" }, svg);
      });
    });
    // กรวยทิศที่มอง
    var c = byId[cur];
    if (c && c.map) {
      cone = el("g", { class: "cone" }, svg);
      el("path", { d: "M0 0 L-6 -11 A12.5 12.5 0 0 1 6 -11 Z" }, cone);
      updateCone();
    }
    // จุดชม
    TOUR.scenes.forEach(function (s) {
      if (!s.map) return;
      var g = el("g", { class: "node" + (s.id === cur ? " current" : ""), tabindex: 0, role: "button" }, svg);
      el("circle", { cx: s.map.x, cy: s.map.y, r: s.id === cur ? 3.2 : 2.4 }, g);
      var title = el("title", {}, g);
      title.textContent = s.title;
      g.addEventListener("click", function () { goTo(s.id); });
      g.addEventListener("keydown", function (e) { if (e.key === "Enter") goTo(s.id); });
    });
  }

  function updateCone() {
    var s = currentScene();
    if (!cone || !s || !s.map) return;
    var heading = yawToBearing(s, viewer.getYaw());
    cone.setAttribute("transform", "translate(" + s.map.x + " " + s.map.y + ") rotate(" + heading + ")");
  }

  /* ---------- โหมดแก้ไข (?edit=1) ช่วยหาค่า yaw / pitch ---------- */

  if (EDIT) {
    var hud = $("edit-hud");
    hud.hidden = false;
    viewer.on("mouseup", function (e) {
      var c = viewer.mouseEventToCoords(e);
      var snippet = "{ yaw: " + c[1].toFixed(1) + ", pitch: " + c[0].toFixed(1) + " }";
      console.log(viewer.getScene(), snippet);
      hud.dataset.click = snippet;
    });
  }

  function editHud() {
    if (!EDIT) return;
    var hud = $("edit-hud");
    hud.textContent =
      "โหมดแก้ไข · scene: " + viewer.getScene() +
      "\nกึ่งกลางจอ  yaw: " + viewer.getYaw().toFixed(1) + "  pitch: " + viewer.getPitch().toFixed(1) +
      "\n(ตั้ง northOffset = yaw ที่หันไปด้านบนแผนผัง)" +
      "\nคลิกล่าสุด: " + (hud.dataset.click || "-");
  }

  /* ---------- วนอัปเดต ---------- */

  var lastYaw = null;
  (function tick() {
    if (viewer.isLoaded && viewer.isLoaded()) {
      var y = viewer.getYaw();
      if (y !== lastYaw) {
        lastYaw = y;
        updateCone();
        updateForwardButton();
        editHud();
      }
    }
    requestAnimationFrame(tick);
  })();

  viewer.on("scenechange", function () { lastYaw = null; updateSceneUI(); });
  viewer.on("load", function () { lastYaw = null; updateSceneUI(); });

  /* ---------- หน้าต้อนรับ ---------- */

  $("tour-title").textContent = TOUR.title;
  $("intro-title").textContent = TOUR.title;
  $("intro-sub").textContent = TOUR.subtitle || "";
  $("btn-start").addEventListener("click", function () {
    $("intro").classList.add("gone");
    setTimeout(function () { $("intro").hidden = true; }, 600);
  });
  if (location.hash.length > 1 || EDIT) $("intro").hidden = true;

  updateSceneUI();
})();
