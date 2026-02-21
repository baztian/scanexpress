const scanButton = document.getElementById("scanButton");
const statusText = document.getElementById("statusText");

async function triggerScan() {
  if (!statusText) return;
  statusText.textContent = "Status: triggering...";

  try {
    const response = await fetch("/api/scan", { method: "POST" });
    let payload;

    try {
      payload = await response.json();
    } catch (error) {
      statusText.textContent = "Status: invalid backend response";
      return;
    }

    const status = payload?.status ?? "unknown";
    const message = payload?.message ?? "No message provided";
    statusText.textContent = `Status: ${status} (${message})`;
  } catch (error) {
    statusText.textContent = "Status: error contacting backend";
  }
}

if (scanButton) {
  scanButton.addEventListener("click", triggerScan);
}
