const els = {
  imageInput: document.querySelector("#imageInput"),
  imageName: document.querySelector("#imageName"),
  sourcePreview: document.querySelector("#sourcePreview"),
  outputPreview: document.querySelector("#outputPreview"),
  processButton: document.querySelector("#processButton"),
  downloadButton: document.querySelector("#downloadButton"),
  candidatesButton: document.querySelector("#candidatesButton"),
  resetButton: document.querySelector("#resetButton"),
  statusText: document.querySelector("#statusText"),
  jsonSettings: document.querySelector("#jsonSettings"),
  autoGenerate: document.querySelector("#autoGenerate"),
  writeExif: document.querySelector("#writeExif"),
  doubleJpeg: document.querySelector("#doubleJpeg"),
  presetMode: document.querySelector("#presetMode"),
  candidateMode: document.querySelector("#candidateMode"),
  routeEDenoise: document.querySelector("#routeEDenoise"),
  routeESharpen: document.querySelector("#routeESharpen"),
  routeEResample: document.querySelector("#routeEResample"),
  denoiseValue: document.querySelector("#denoiseValue"),
  sharpenValue: document.querySelector("#sharpenValue"),
  resampleValue: document.querySelector("#resampleValue"),
};

const state = {
  image: null,
  output: null,
};

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function setBusy(isBusy, text) {
  els.processButton.disabled = isBusy || !state.image;
  els.candidatesButton.disabled = isBusy || !state.image;
  els.downloadButton.disabled = isBusy || !state.output;
  els.statusText.textContent = text;
}

function applyPreset(settings) {
  if (els.presetMode.value === "quality") {
    Object.assign(settings, {
      routeEDenoise: 0.55,
      routeESharpen: 0.10,
      routeEResample: 4,
    });
  }
  if (els.presetMode.value === "balanced") {
    Object.assign(settings, {
      routeEDenoise: 0.70,
      routeESharpen: 0.055,
      routeEResample: 4,
    });
  }
  if (els.presetMode.value === "score") {
    Object.assign(settings, {
      routeEDenoise: 0.80,
      routeESharpen: 0.035,
      routeEResample: 5,
      routeEHighlightBloom: 0.06,
      routeESeed: 521,
    });
  }
}

function addRangeOverride(settings, input) {
  if (Number(input.value) > 0) {
    settings[input.dataset.setting] = Number(input.value);
  }
}

function currentSettings() {
  const settings = {
    route: "auto",
    autoRoute: true,
    writeExif: els.writeExif.checked,
  };
  if (els.doubleJpeg.checked) settings.doubleJpeg = true;
  applyPreset(settings);
  addRangeOverride(settings, els.routeEDenoise);
  addRangeOverride(settings, els.routeESharpen);
  addRangeOverride(settings, els.routeEResample);

  const extra = els.jsonSettings.value.trim();
  if (extra) Object.assign(settings, JSON.parse(extra));
  return settings;
}

function updateRangeLabels() {
  els.denoiseValue.textContent = Number(els.routeEDenoise.value) ? Number(els.routeEDenoise.value).toFixed(2) : "自动";
  els.sharpenValue.textContent = Number(els.routeESharpen.value) ? Number(els.routeESharpen.value).toFixed(3) : "自动";
  els.resampleValue.textContent = Number(els.routeEResample.value) ? els.routeEResample.value : "自动";
}

async function handleFile(file) {
  if (!file) return;
  const dataUrl = await readFile(file);
  state.image = { file, dataUrl };
  state.output = null;
  els.imageName.textContent = file.name;
  els.sourcePreview.src = dataUrl;
  els.outputPreview.removeAttribute("src");
  setBusy(false, "已上传。");
  if (els.autoGenerate.checked) await processImage();
}

async function postJson(endpoint) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image: state.image.dataUrl,
      settings: currentSettings(),
      candidateMode: els.candidateMode.value,
    }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function processImage() {
  if (!state.image) return;
  setBusy(true, "正在生成单张...");
  try {
    const result = await postJson("/process");
    state.output = result.image;
    els.outputPreview.src = result.image;
    const routeText = result.route ? `路线 ${result.route}` : "自动路线";
    const reasonText = result.autoReason ? ` / ${result.autoReason}` : "";
    const channelText = result.autoChannel ? ` / ${result.autoChannel}` : "";
    const decisionText = result.autoDecision ? ` / ${result.autoDecision}` : "";
    setBusy(false, `单张生成完成：${routeText}${reasonText}${channelText}${decisionText}`);
  } catch (error) {
    console.error(error);
    setBusy(false, "生成失败，请检查参数或本地服务。");
  }
}

function downloadDataUrl(dataUrl, filename) {
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  link.click();
}

async function downloadCandidates() {
  if (!state.image) return;
  setBusy(true, "正在生成候选包...");
  try {
    const result = await postJson("/candidates");
    downloadDataUrl(result.archive, "texture-lab-candidates.zip");
    setBusy(false, "候选包已下载。");
  } catch (error) {
    console.error(error);
    setBusy(false, "候选包生成失败，请检查参数或本地服务。");
  }
}

function resetSettings() {
  els.jsonSettings.value = "";
  els.writeExif.checked = false;
  els.doubleJpeg.checked = false;
  els.presetMode.value = "auto";
  els.candidateMode.value = "adaptive";
  els.routeEDenoise.value = "0";
  els.routeESharpen.value = "0";
  els.routeEResample.value = "0";
  updateRangeLabels();
  setBusy(false, state.image ? "覆盖已清空。" : "等待上传。");
}

els.imageInput.addEventListener("change", (event) => handleFile(event.target.files[0]));
els.processButton.addEventListener("click", processImage);
els.candidatesButton.addEventListener("click", downloadCandidates);
els.downloadButton.addEventListener("click", () => {
  if (state.output) downloadDataUrl(state.output, "texture-lab-output.jpg");
});
els.resetButton.addEventListener("click", resetSettings);
[els.routeEDenoise, els.routeESharpen, els.routeEResample].forEach((input) => {
  input.addEventListener("input", updateRangeLabels);
});

document.body.addEventListener("dragover", (event) => event.preventDefault());
document.body.addEventListener("drop", (event) => {
  event.preventDefault();
  const file = [...event.dataTransfer.files].find((item) => item.type.startsWith("image/"));
  if (file) handleFile(file);
});

updateRangeLabels();
