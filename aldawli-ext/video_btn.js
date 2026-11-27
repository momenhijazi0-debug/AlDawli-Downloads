(() => {
  if (window.top !== window) return;
  const dismissed = new WeakSet();
  let activeVideo = null;
  let hideTimer = null;
  let btnEnabled = true;

  function syncConfig() {
    try {
      chrome.runtime.sendMessage({ action: "get_config" }, (cfg) => {
        if (chrome.runtime.lastError) return;
        if (cfg && typeof cfg.show_video_btn === "boolean") {
          btnEnabled = cfg.show_video_btn;
          if (!btnEnabled) {
            btn.style.display = "none";
            activeVideo = null;
          }
        }
      });
    } catch (e) {}
  }
  syncConfig();
  window.addEventListener("focus", syncConfig);
  setInterval(syncConfig, 8000);

  const btn = document.createElement("div");
  btn.id = "aldawli-vid-float";
  btn.style.cssText = [
    "position:fixed",
    "z-index:2147483647",
    "display:none",
    "align-items:center",
    "gap:6px",
    "padding:6px 11px",
    "border-radius:999px",
    "background:rgba(15,23,42,0.88)",
    "backdrop-filter:blur(8px)",
    "color:#fff",
    "border:1px solid rgba(124,155,255,0.55)",
    "box-shadow:0 6px 20px rgba(0,0,0,0.35)",
    "font:600 12.5px/1.2 'Segoe UI',Tahoma,sans-serif",
    "direction:rtl",
    "cursor:pointer",
    "user-select:none",
    "transition:opacity .15s,transform .15s"
  ].join(";");

  const mainSpan = document.createElement("span");
  mainSpan.textContent = "⬇ تحميل بواسطة الدولي";
  mainSpan.style.cssText = "display:inline-flex;align-items:center;gap:5px";

  const closeSpan = document.createElement("span");
  closeSpan.textContent = "×";
  closeSpan.title = "إخفاء";
  closeSpan.style.cssText = "margin-right:4px;padding:0 4px;font-size:15px;opacity:.75;border-radius:50%";
  closeSpan.onclick = (e) => {
    e.stopPropagation();
    if (activeVideo) dismissed.add(activeVideo);
    btn.style.display = "none";
    activeVideo = null;
  };

  btn.appendChild(mainSpan);
  btn.appendChild(closeSpan);

  btn.onclick = (e) => {
    e.stopPropagation();
    const orig = mainSpan.textContent;
    mainSpan.textContent = "⏳ جارٍ الفتح...";
    try {
      chrome.runtime.sendMessage({ action: "download_video", url: location.href });
    } catch (err) {}
    setTimeout(() => { mainSpan.textContent = orig; }, 1400);
  };

  btn.onmouseenter = () => { clearTimeout(hideTimer); };
  btn.onmouseleave = () => { scheduleHide(); };

  function ensureAttached() {
    if (!document.documentElement.contains(btn)) {
      document.documentElement.appendChild(btn);
    }
  }

  function positionOn(video) {
    if (!video || dismissed.has(video)) return;
    const r = video.getBoundingClientRect();
    if (r.width < 200 || r.height < 120 || r.bottom < 0 || r.top > window.innerHeight) {
      btn.style.display = "none";
      return;
    }
    ensureAttached();
    const top = Math.max(8, r.top + 10);
    const left = Math.min(window.innerWidth - 185, Math.max(8, r.right - 175));
    btn.style.top = top + "px";
    btn.style.left = left + "px";
    btn.style.display = "inline-flex";
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      btn.style.display = "none";
    }, 600);
  }

  document.addEventListener("mousemove", (e) => {
    if (!btnEnabled) { btn.style.display = "none"; return; }
    const vids = document.querySelectorAll("video");
    let hit = null;
    for (const v of vids) {
      if (dismissed.has(v)) continue;
      const r = v.getBoundingClientRect();
      if (r.width >= 200 && r.height >= 120 &&
          e.clientX >= r.left && e.clientX <= r.right &&
          e.clientY >= r.top && e.clientY <= r.bottom) {
        hit = v;
        break;
      }
    }
    if (hit) {
      clearTimeout(hideTimer);
      activeVideo = hit;
      positionOn(hit);
    } else if (btn.style.display !== "none" && !btn.matches(":hover")) {
      scheduleHide();
    }
  }, { passive: true });

  window.addEventListener("scroll", () => {
    if (activeVideo && btn.style.display !== "none") positionOn(activeVideo);
  }, { passive: true });
})();
