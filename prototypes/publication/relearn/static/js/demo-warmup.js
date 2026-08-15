(() => {
  "use strict";

  const button = document.querySelector("[data-demo-start]");
  const status = document.querySelector("[data-demo-status]");
  const detail = document.querySelector("[data-demo-detail]");
  if (
    !(button instanceof HTMLButtonElement) ||
    !(status instanceof HTMLElement) ||
    !(detail instanceof HTMLElement)
  )
    return;

  const demoUrl = button.dataset.demoUrl;
  const requestTimeoutMs = 8_000;

  const show = (headline, explanation) => {
    status.hidden = false;
    detail.hidden = false;
    status.textContent = headline;
    detail.textContent = explanation;
  };

  const delay = (milliseconds) =>
    new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  const checkHealth = async () => {
    const controller = new AbortController();
    const requestTimeout = window.setTimeout(
      () => controller.abort(),
      requestTimeoutMs,
    );
    try {
      const response = await fetch(`${demoUrl}/api/health`, {
        method: "GET",
        mode: "cors",
        credentials: "omit",
        cache: "no-store",
        redirect: "error",
        referrerPolicy: "no-referrer",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) return false;
      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.toLowerCase().startsWith("application/json"))
        return false;
      const payload = await response.json();
      return (
        payload !== null &&
        typeof payload === "object" &&
        payload.status === "ok"
      );
    } catch {
      return false;
    } finally {
      window.clearTimeout(requestTimeout);
    }
  };

  const startDemo = async () => {
    const maximumAttempts = Number.parseInt(
      button.dataset.demoMaximumAttempts ?? "12",
      10,
    );
    const totalTimeoutMs = Number.parseInt(
      button.dataset.demoTotalTimeoutMs ?? "90000",
      10,
    );
    button.disabled = true;
    button.textContent = "Demo wird gestartet …";
    button.setAttribute("aria-busy", "true");
    show(
      "Demo wird vorbereitet",
      "Die Demo fährt gerade aus dem Ruhezustand hoch. Diese Seite prüft nur, ob sie bereit ist.",
    );
    const deadline = Date.now() + totalTimeoutMs;

    for (
      let attempt = 1;
      attempt <= maximumAttempts && Date.now() < deadline;
      attempt += 1
    ) {
      if (await checkHealth()) {
        show("Demo ist bereit", "Weiterleitung …");
        window.location.assign(`${demoUrl}/`);
        return;
      }
      if (attempt < maximumAttempts && Date.now() < deadline) {
        const remainingSeconds = Math.max(
          1,
          Math.ceil((deadline - Date.now()) / 1000),
        );
        show(
          "Demo wird vorbereitet",
          `Noch nicht bereit. Erneuter Versuch in Kürze (höchstens noch ${remainingSeconds} Sekunden).`,
        );
        await delay(
          Math.min(
            2_000 + attempt * 500,
            7_000,
            Math.max(0, deadline - Date.now()),
          ),
        );
      }
    }

    show(
      "Demo konnte nicht gestartet werden",
      "Bitte versuche es erneut. Wenn der Fehler bleibt, nutze das Handbuch oder das Repository als Einstieg.",
    );
    button.disabled = false;
    button.textContent = "Erneut versuchen";
    button.removeAttribute("aria-busy");
    button.focus();
  };

  button.addEventListener("click", () => void startDemo());
})();
