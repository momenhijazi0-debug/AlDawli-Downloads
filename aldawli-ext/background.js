const BASE = "http://127.0.0.1:8765";

async function collectCookiesFor(urls) {
  const map = new Map();
  for (const u of urls) {
    if (!u || !u.startsWith("http")) continue;
    try {
      const list = await chrome.cookies.getAll({ url: u });
      for (const c of list) {
        map.set(c.name, c.value);
      }
    } catch (e) {}
  }
  return [...map.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
}

async function getHeaders(url, referrer = "", origUrl = "") {
  const headers = { "User-Agent": navigator.userAgent };
  const cookieUrls = [url];
  if (origUrl && origUrl !== url) cookieUrls.push(origUrl);
  if (referrer) cookieUrls.push(referrer);

  if (/google\.com|googleusercontent\.com/i.test(url + " " + origUrl)) {
    cookieUrls.push("https://drive.google.com/", "https://drive.usercontent.google.com/");
  }

  const cookieHeader = await collectCookiesFor(cookieUrls);
  if (cookieHeader) headers["Cookie"] = cookieHeader;
  if (referrer) headers["Referer"] = referrer;
  return headers;
}

async function sendToAldawli(url, referrer = "", origUrl = "") {
  try {
    const headers = await getHeaders(url, referrer, origUrl);
    const res = await fetch(`${BASE}/api/ext/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: [url], headers }),
      signal: AbortSignal.timeout(2000)
    });
    return res.ok;
  } catch (e) {
    return false;
  }
}

async function sendVideoToAldawli(url, referrer = "") {
  try {
    const headers = await getHeaders(url, referrer);
    const res = await fetch(`${BASE}/api/ext/video`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, headers }),
      signal: AbortSignal.timeout(2000)
    });
    return res.ok;
  } catch (e) {
    return false;
  }
}

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  const url = item.finalUrl || item.url;
  if (!url || !url.startsWith("http") || url.startsWith(BASE) || url.includes("contribution.usercontent.google.com")) {
    suggest();
    return false;
  }

  sendToAldawli(url, item.referrer || "", item.url || "").then((ok) => {
    if (ok) {
      chrome.downloads.cancel(item.id, () => {
        chrome.downloads.erase({ id: item.id });
      });
    } else {
      suggest();
    }
  });

  return true;
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "aldawli-dl",
      title: "تنزيل الملف عبر الدولي للتحميلات",
      contexts: ["link"]
    });
    chrome.contextMenus.create({
      id: "aldawli-vid",
      title: "تحميل الفيديو عبر الدولي للتحميلات (يوتيوب / إنستغرام)",
      contexts: ["page", "link", "video"]
    });
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const pageUrl = tab ? tab.url : "";
  if (info.menuItemId === "aldawli-dl" && info.linkUrl) {
    if (info.linkUrl.toLowerCase().startsWith("magnet:?")) {
      fetch(`${BASE}/api/ext/torrent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uri: info.linkUrl })
      }).catch(() => {});
    } else {
      sendToAldawli(info.linkUrl, pageUrl);
    }
  } else if (info.menuItemId === "aldawli-vid") {
    const target = info.linkUrl || info.pageUrl || pageUrl;
    if (target) sendVideoToAldawli(target, pageUrl);
  }
});


chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.action === "download_video") {
    const targetUrl = msg.url || (sender && sender.tab && sender.tab.url) || "";
    if (targetUrl) {
      sendVideoToAldawli(targetUrl, sender && sender.tab ? sender.tab.url : "");
    }
    sendResponse({ ok: true });
  } else if (msg && msg.action === "get_config") {
    fetch(`${BASE}/api/ext/config`)
      .then((r) => r.ok ? r.json() : { show_video_btn: true })
      .then((cfg) => sendResponse(cfg))
      .catch(() => sendResponse({ show_video_btn: true }));
    return true;
  }
});
