const scanButton = document.getElementById("scanButton");
const statusText = document.getElementById("statusText");

async function triggerScan() {
  if (!statusText || !scanButton) return;
  scanButton.disabled = true;
  statusText.textContent = "Status: triggering...";

  try {
    const response = await fetch("/api/scan/stream", { method: "POST" });
    if (!response.ok || !response.body) {
      statusText.textContent = "Status: invalid backend response";
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let bufferedText = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      bufferedText += decoder.decode(value, { stream: true });
      const lines = bufferedText.split("\n");
      bufferedText = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.trim()) continue;

        let payload;
        try {
          payload = JSON.parse(line);
        } catch (error) {
          statusText.textContent = "Status: invalid backend response";
          continue;
        }

        const status = payload?.status ?? "unknown";
        const message = payload?.message ?? "No message provided";
        statusText.textContent = `Status: ${status} (${message})`;
      }
    }
  } catch (error) {
    statusText.textContent = "Status: error contacting backend";
  } finally {
    scanButton.disabled = false;
  }
}

if (scanButton) {
  scanButton.addEventListener("click", triggerScan);
}
