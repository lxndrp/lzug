(() => {
  "use strict";
  const button = document.querySelector("[data-demo-start]");
  const status = document.querySelector("[data-demo-status]");
  const detail = document.querySelector("[data-demo-detail]");
  if (!(button instanceof HTMLButtonElement) || !(status instanceof HTMLElement) || !(detail instanceof HTMLElement)) return;
  const demoUrl = button.dataset.demoUrl;
  const show = (headline, explanation) => { status.hidden = false; detail.hidden = false; status.textContent = headline; detail.textContent = explanation; };
  const delay = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  const checkReadiness = async () => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`${demoUrl}/api/ready`, { method: "GET", mode: "cors", credentials: "omit", cache: "no-store", redirect: "error", referrerPolicy: "no-referrer", headers: { Accept: "application/json" }, signal: controller.signal });
      if (!response.ok || !(response.headers.get("content-type") ?? "").toLowerCase().startsWith("application/json")) return false;
      const payload = await response.json();
      return payload !== null && typeof payload === "object" && payload.status === "ready";
    } catch { return false; } finally { window.clearTimeout(timeout); }
  };
  button.addEventListener("click", async () => {
    const maximumAttempts = Number.parseInt(button.dataset.demoMaximumAttempts ?? "12", 10);
    const deadline = Date.now() + Number.parseInt(button.dataset.demoTotalTimeoutMs ?? "90000", 10);
    button.disabled = true; button.textContent = "Demo wird gestartet …"; button.setAttribute("aria-busy", "true");
    show("Demo wird vorbereitet", "Die Demo fährt gerade aus dem Ruhezustand hoch. Diese Seite prüft nur, ob sie bereit ist.");
    for (let attempt = 1; attempt <= maximumAttempts && Date.now() < deadline; attempt += 1) {
      if (await checkReadiness()) { show("Demo ist bereit", "Weiterleitung …"); window.location.assign(`${demoUrl}/`); return; }
      if (attempt < maximumAttempts && Date.now() < deadline) await delay(Math.min(2000 + attempt * 500, 7000, Math.max(0, deadline - Date.now())));
    }
    show("Demo konnte nicht gestartet werden", "Bitte versuche es erneut. Wenn der Fehler bleibt, nutze das Handbuch oder das Repository als Einstieg.");
    button.disabled = false; button.textContent = "Erneut versuchen"; button.removeAttribute("aria-busy"); button.focus();
  });
})();
