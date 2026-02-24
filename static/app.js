const scanButton = document.getElementById("scanButton");
const statusText = document.getElementById("statusText");
const deviceSelect = document.getElementById("deviceSelect");
const deviceDetails = document.getElementById("deviceDetails");
let deviceMap = new Map();
let selectedDeviceName = null;

function renderDeviceDetails(selectedDevice) {
  if (!deviceDetails) return;

  if (!selectedDevice) {
    deviceDetails.textContent = "No device selected.";
    return;
  }

  const detailLines = [
    `Name: ${selectedDevice.device_name ?? "n/a"}`,
    `Configured ID: ${selectedDevice.device_id ?? "n/a"}`,
    `Runtime ID: ${selectedDevice.scanimage_device_name ?? "n/a"}`,
    `Scan command: ${selectedDevice.scan_command ?? "n/a"}`,
    `Scan timeout: ${selectedDevice.scan_timeout_seconds ?? "n/a"}`,
  ];

  const scanimageParams = selectedDevice.scanimage_params ?? {};
  const scanimageParamKeys = Object.keys(scanimageParams).sort();
  if (scanimageParamKeys.length > 0) {
    detailLines.push("scanimage params:");
    for (const paramKey of scanimageParamKeys) {
      detailLines.push(`- ${paramKey}: ${scanimageParams[paramKey]}`);
    }
  } else {
    detailLines.push("scanimage params: none");
  }

  deviceDetails.textContent = detailLines.join("\n");
}

function renderDeviceSelect(deviceNames, selectedDeviceName) {
  if (!deviceSelect) return;

  deviceSelect.innerHTML = "";
  for (const deviceName of deviceNames) {
    const option = document.createElement("option");
    option.value = deviceName;
    option.textContent = deviceName;
    if (deviceName === selectedDeviceName) {
      option.selected = true;
    }
    deviceSelect.appendChild(option);
  }

  deviceSelect.disabled = deviceNames.length === 0;
}

function applyDeviceConfigurations(payload) {
  const devices = payload?.devices ?? [];
  deviceMap = new Map(devices.map((device) => [device.device_name, device]));
  selectedDeviceName = payload?.selected_device_name ?? null;

  const deviceNames = devices.map((device) => device.device_name);
  renderDeviceSelect(deviceNames, selectedDeviceName);
  renderDeviceDetails(deviceMap.get(selectedDeviceName) ?? null);
}

async function loadDeviceConfigurations() {
  try {
    const response = await fetch("/api/device-configurations", { method: "GET" });
    if (!response.ok) {
      statusText.textContent = "Status: failed to load device configuration";
      return;
    }

    const payload = await response.json();
    applyDeviceConfigurations(payload);
  } catch (_error) {
    statusText.textContent = "Status: error loading device configuration";
  }
}

async function selectDeviceConfiguration(deviceName) {
  selectedDeviceName = deviceName;
  renderDeviceDetails(deviceMap.get(selectedDeviceName) ?? null);
  statusText.textContent = `Status: selected (${selectedDeviceName})`;
}

async function triggerScan() {
  if (!statusText || !scanButton) return;
  scanButton.disabled = true;
  statusText.textContent = "Status: triggering...";

  try {
    const response = await fetch("/api/scan/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ device_name: selectedDeviceName }),
    });
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

if (deviceSelect) {
  deviceSelect.addEventListener("change", async (event) => {
    const nextDeviceName = event?.target?.value;
    if (!nextDeviceName) return;
    await selectDeviceConfiguration(nextDeviceName);
  });
}

void loadDeviceConfigurations();
