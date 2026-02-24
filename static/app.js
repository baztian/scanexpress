const scanButton = document.getElementById("scanButton");
const statusText = document.getElementById("statusText");
const deviceSelect = document.getElementById("deviceSelect");
const deviceDetails = document.getElementById("deviceDetails");
let deviceMap = new Map();
let selectedDeviceName = null;
let currentStatus = "idle";
let currentMessage = "idle";
const timeoutState = {
  phase: "idle",
  countdownStartSeconds: 15,
  scan: {
    timeoutSeconds: null,
    startedAtMs: null,
    label: "scanimage",
  },
  upload: {
    timeoutSeconds: null,
    startedAtMs: null,
    label: "paperless",
  },
};

function clearTimeoutCountdownState() {
  timeoutState.phase = "idle";
  timeoutState.countdownStartSeconds = 15;
  timeoutState.scan.timeoutSeconds = null;
  timeoutState.scan.startedAtMs = null;
  timeoutState.upload.timeoutSeconds = null;
  timeoutState.upload.startedAtMs = null;
}

function setStatus(status, message) {
  currentStatus = status;
  currentMessage = message;
  renderCurrentStatus();
}

function buildTimeoutSuffixForTarget(nowMs, targetState) {
  if (!Number.isFinite(targetState.timeoutSeconds) || targetState.startedAtMs === null) {
    return "";
  }

  const elapsedSeconds = (nowMs - targetState.startedAtMs) / 1000;
  if (
    elapsedSeconds < timeoutState.countdownStartSeconds ||
    elapsedSeconds >= targetState.timeoutSeconds
  ) {
    return "";
  }

  const remainingSeconds = Math.max(Math.ceil(targetState.timeoutSeconds - elapsedSeconds), 0);
  return ` (timeout ${targetState.label}: ${remainingSeconds}s)`;
}

function formatTimeoutSuffix() {
  const nowMs = Date.now();
  if (timeoutState.phase === "scanning") {
    return buildTimeoutSuffixForTarget(nowMs, timeoutState.scan);
  }
  if (timeoutState.phase === "uploading") {
    return buildTimeoutSuffixForTarget(nowMs, timeoutState.upload);
  }
  return "";
}

function renderCurrentStatus() {
  if (!statusText) return;
  statusText.textContent = `Status: ${currentStatus} (${currentMessage}${formatTimeoutSuffix()})`;
}

setInterval(() => {
  if (!statusText) return;
  if (timeoutState.phase !== "scanning" && timeoutState.phase !== "uploading") return;
  renderCurrentStatus();
}, 1000);

function applyTimeoutMetadata(payload) {
  const nextCountdownStart = Number(payload?.timeout_countdown_start_seconds);
  if (Number.isFinite(nextCountdownStart) && nextCountdownStart >= 0) {
    timeoutState.countdownStartSeconds = nextCountdownStart;
  }

  const nextScanTimeout = Number(payload?.scan_timeout_seconds);
  if (Number.isFinite(nextScanTimeout) && nextScanTimeout > 0) {
    timeoutState.scan.timeoutSeconds = nextScanTimeout;
  }

  const nextPaperlessTimeout = Number(payload?.paperless_timeout_seconds);
  if (Number.isFinite(nextPaperlessTimeout) && nextPaperlessTimeout > 0) {
    timeoutState.upload.timeoutSeconds = nextPaperlessTimeout;
  }
}

function updatePhaseState(payload, status, nowMs) {
  if (status === "scanning") {
    timeoutState.phase = "scanning";
    if (timeoutState.scan.startedAtMs === null || Number.isFinite(Number(payload?.page_count))) {
      timeoutState.scan.startedAtMs = nowMs;
    }
    return;
  }

  if (status === "uploading") {
    timeoutState.phase = "uploading";
    if (timeoutState.upload.startedAtMs === null) {
      timeoutState.upload.startedAtMs = nowMs;
    }
    return;
  }

  if (status === "processing") {
    timeoutState.phase = "processing";
    return;
  }

  if (payload?.complete || status === "ok" || status === "error") {
    timeoutState.phase = "done";
  }
}

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
  clearTimeoutCountdownState();
  setStatus("triggering", "triggering...");

  try {
    const response = await fetch("/api/scan/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ device_name: selectedDeviceName }),
    });
    if (!response.ok || !response.body) {
      setStatus("error", "invalid backend response");
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
          setStatus("error", "invalid backend response");
          continue;
        }

        const status = payload?.status ?? "unknown";
        const message = payload?.message ?? "No message provided";
        const nowMs = Date.now();
        applyTimeoutMetadata(payload);
        updatePhaseState(payload, status, nowMs);
        setStatus(status, message);
      }
    }
  } catch (error) {
    clearTimeoutCountdownState();
    setStatus("error", "error contacting backend");
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
