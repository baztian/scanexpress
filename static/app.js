const scanButton = document.getElementById("scanButton");
const statusText = document.getElementById("statusText");

async function triggerScan() {
  if (!statusText) return;
  statusText.textContent = "Status: triggering...";

  try {
    const response = await fetch("/api/scan", { method: "POST" });
    const payload = await response.json();
    statusText.textContent = `Status: ${payload.status} (${payload.message})`;
  } catch (error) {
    statusText.textContent = "Status: error contacting backend";
  }
}

if (scanButton) {
  scanButton.addEventListener("click", triggerScan);
}
