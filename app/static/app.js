// 视频帧序列导出前端逻辑
const $ = (id) => document.getElementById(id);
let selectedFile = null, jobId = null, currentDir = "color", dirCache = {};
let playing = false, playTimer = null, playIndex = 0;

// ---------- 上传 ----------
const drop = $("drop"), fileInput = $("fileInput");
drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  if (e.dataTransfer.files.length) pickFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) pickFile(fileInput.files[0]);
});
function pickFile(f) {
  selectedFile = f;
  $("fileName").textContent = f.name;
  $("submitBtn").disabled = false;
}

// ---------- 开关样式 ----------
document.querySelectorAll("#toggles input").forEach((cb) => {
  cb.addEventListener("change", () =>
    cb.closest(".toggle").classList.toggle("on", cb.checked));
});

// ---------- 提交任务 ----------
$("submitBtn").addEventListener("click", () => {
  const fd = new FormData();
  fd.append("file", selectedFile);
  fd.append("preset", $("preset").value);
  ["fps", "lineart_bg", "canny_low", "canny_high", "line_width", "min_component",
   "keyframe_threshold", "mask_threshold", "color_levels", "workers"].forEach((k) =>
    fd.append(k, $(k).value));
  document.querySelectorAll("#toggles input").forEach((cb) =>
    fd.append(cb.dataset.key, cb.checked ? "true" : "false"));

  $("submitBtn").disabled = true;
  $("progressWrap").style.display = "block";
  $("errorText").textContent = "";
  fetch("/api/jobs", { method: "POST", body: fd })
    .then((r) => r.json())
    .then((job) => {
      if (job.detail || job.id === undefined) throw new Error(JSON.stringify(job));
      jobId = job.id;
      listenEvents();
    })
    .catch((err) => {
      $("errorText").textContent = "提交失败：" + err.message;
      $("submitBtn").disabled = false;
    });
});

// ---------- SSE 进度 ----------
function listenEvents() {
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  es.onmessage = (e) => {
    const j = JSON.parse(e.data);
    $("progressBar").style.width = j.progress + "%";
    $("phaseText").textContent = j.status + (j.phase ? " · " + j.phase : "");
    $("frameText").textContent = `${j.done_frames} / ${j.total_frames}`;
    if (j.status === "done") {
      es.close();
      $("submitBtn").disabled = false;
      showResult();
    } else if (j.status === "error") {
      es.close();
      $("submitBtn").disabled = false;
      $("errorText").textContent = "处理失败：" + j.error;
    }
  };
}

// ---------- 结果展示 ----------
async function showResult() {
  $("result").style.display = "block";
  $("downloadBtn").onclick = () =>
    window.open(`/api/jobs/${jobId}/download`, "_blank");
  const dirs = await fetch(`/api/jobs/${jobId}/dirs`).then((r) => r.json());
  dirCache = dirs;
  const tabs = $("tabs");
  tabs.innerHTML = "";
  Object.keys(dirs).forEach((name) => {
    const t = document.createElement("div");
    t.className = "tab" + (name === currentDir ? " active" : "");
    t.textContent = `${name} (${dirs[name]})`;
    t.onclick = () => {
      currentDir = name;
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      loadGallery();
    };
    tabs.appendChild(t);
  });
  if (!dirs[currentDir]) currentDir = Object.keys(dirs)[0];
  loadGallery();
}

async function loadGallery() {
  const files = await fetch(`/api/jobs/${jobId}/files/${currentDir}`)
    .then((r) => r.json());
  const gallery = $("gallery");
  gallery.innerHTML = "";
  $("emptyTip").style.display = files.length ? "none" : "block";
  files.forEach((f) => {
    const img = document.createElement("img");
    img.src = `/api/jobs/${jobId}/raw/${currentDir}/${f}`;
    img.loading = "lazy";
    gallery.appendChild(img);
  });
}

function rawUrl(dir, file) {
  return `/api/jobs/${jobId}/raw/${dir}/${file}`;
}
async function fileList(dir) {
  return fetch(`/api/jobs/${jobId}/files/${dir}`).then((r) => r.json());
}

// ---------- 帧序列播放器 ----------
$("playBtn").addEventListener("click", async () => {
  stopPlay();
  const stage = $("stage");
  stage.style.display = "block";
  $("compareRange").style.display = "none";
  $("labelTop").style.display = "none";
  $("labelBottom").style.display = "none";
  const files = await fileList(currentDir);
  if (!files.length) return;
  $("stageTop").src = rawUrl(currentDir, files[0]);
  $("stageBottom").style.display = "none";
  playIndex = 0;
  playing = true;
  $("playPause").textContent = "暂停";
  const tick = () => {
    if (!playing) return;
    playIndex = (playIndex + 1) % files.length;
    $("stageTop").src = rawUrl(currentDir, files[playIndex]);
  };
  const loop = () => {
    if (!playing) return;
    tick();
    playTimer = setTimeout(loop, 1000 / Math.max(1, $("playFps").value));
  };
  playTimer = setTimeout(loop, 1000 / Math.max(1, $("playFps").value));
});

// ---------- 对比滑块 ----------
$("compareBtn").addEventListener("click", async () => {
  stopPlay();
  const stage = $("stage");
  stage.style.display = "block";
  $("compareRange").style.display = "block";
  $("labelTop").style.display = "block";
  $("labelBottom").style.display = "block";
  $("stageBottom").style.display = "block";
  const cur = await fileList(currentDir);
  const color = await fileList("color");
  if (!cur.length) return;
  $("stageTop").src = rawUrl(currentDir, cur[0]);
  $("stageBottom").src = rawUrl("color", color[0]);
  $("labelTop").textContent = currentDir;
  $("labelBottom").textContent = "color";
});

$("compareRange").addEventListener("input", (e) => {
  const v = e.target.value;
  $("stageTop").style.clipPath = `inset(0 ${100 - v}% 0 0)`;
});

$("playPause").addEventListener("click", () => {
  if (playing) {
    playing = false;
    clearTimeout(playTimer);
    $("playPause").textContent = "播放";
  } else {
    playing = true;
    $("playPause").textContent = "暂停";
  }
});

function stopPlay() {
  playing = false;
  clearTimeout(playTimer);
}
