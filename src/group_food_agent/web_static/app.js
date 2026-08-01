const $ = (id) => document.getElementById(id);
const form = $("order-form");
const photoInput = $("photo");
const preview = $("photo-preview");
const notes = $("notes");
const submitButton = $("submit-button");
const demoButton = $("demo-button");
const statusLine = $("form-status");
const photoDrop = $("photo-drop");
const submitArrow = submitButton.querySelector(".button-arrow");
let previewUrl = null;
let coordinates = null;
let locationPermission = "unavailable";
let latestTerminalJson = null;

const krw = new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 });
const number = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 });

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function append(parent, ...children) {
  children.filter(Boolean).forEach((child) => parent.appendChild(child));
  return parent;
}

function confidence(value) {
  const badge = element("span", "confidence");
  if (value >= .8) badge.textContent = "신뢰도 높음";
  else if (value >= .6) { badge.classList.add("medium"); badge.textContent = "신뢰도 보통"; }
  else { badge.classList.add("low"); badge.textContent = "신뢰도 낮음"; }
  return badge;
}

function setStatus(message = "", state = "") {
  statusLine.textContent = message;
  if (state) statusLine.dataset.state = state;
  else delete statusLine.dataset.state;
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  demoButton.disabled = isLoading;
  photoInput.disabled = isLoading;
  submitButton.dataset.loading = String(isLoading);
  submitArrow.textContent = isLoading ? "↻" : "→";
}

function metric(label, value, extra) {
  const item = element("div", "metric");
  append(item, element("span", "", label), element("strong", "", value));
  if (extra) item.appendChild(extra);
  return item;
}

function servings(milli) { return `${number.format((milli || 0) / 1000)}인분`; }

function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

function renderScene(data) {
  const host = $("scene-content");
  clear(host);
  const scene = data.scene_analysis;
  if (!scene) {
    host.appendChild(element("div", "notice", "텍스트 전용 요청입니다. 사진 관찰값 없이 사용자가 제공한 정보만 계산에 사용했습니다."));
    return;
  }
  const grid = element("div", "metric-grid");
  const resolvedAttendance = data.plan_result?.group_analysis?.actual_attendance
    ?? scene.explicit_total_people
    ?? (scene.visible_people_confidence >= .8 && scene.visible_people !== null
      ? scene.visible_people + (scene.additional_people || 0)
      : null);
  append(grid,
    metric("사진에서 확인한 인원", scene.visible_people === null ? "확인 불가" : `${scene.visible_people}명`, confidence(scene.visible_people_confidence || 0)),
    metric("추가 예정 인원", `${scene.additional_people || 0}명`),
    metric("최종 예상 인원", resolvedAttendance === null ? "확인 필요" : `${resolvedAttendance}명`),
    metric("식사 상황", scene.meal_context || "미확정", confidence(scene.meal_context_confidence || 0)),
    metric("공간", scene.environment_label || "미확정"),
    metric("기존 음식 크레딧", servings(data.existing_food_credit?.total_credited_servings_milli || 0))
  );
  host.appendChild(grid);
  if (scene.existing_food?.length) {
    scene.existing_food.forEach((food) => {
      const credit = data.existing_food_credit?.lines?.find((line) => line.observation_id === food.observation_id);
      const row = element("div", "order-line");
      const left = element("div");
      append(left, element("strong", "", food.label), element("span", "", `${food.estimated_units_min}–${food.estimated_units_max} ${food.unit} · 잔량 ${Math.round(food.remaining_ratio_min * 100)}–${Math.round(food.remaining_ratio_max * 100)}%`));
      const right = element("div");
      append(right, confidence(food.evidence.confidence), element("span", "", credit?.accepted ? ` 반영 ${servings(credit.credited_servings_milli)}` : " 계산 미반영"));
      append(row, left, right); host.appendChild(row);
    });
  } else {
    host.appendChild(element("div", "notice", "계산에 반영할 기존 음식이 관찰되지 않았습니다."));
  }
  (data.conflict_resolutions || []).forEach((item) => host.appendChild(element("div", "notice", `정정 반영: ${item.source_text} → ${item.accepted_value}`)));
  if (data.context_used?.history) host.appendChild(element("div", "notice", `준비된 데모 이력 · ${data.context_used.history.summary}`));
}

function renderResult(data) {
  const host = $("result-content"); clear(host);
  const result = data.plan_result;
  latestTerminalJson = result || data.boundary_outcome;
  $("result-json").textContent = JSON.stringify(latestTerminalJson, null, 2);
  if (!result || result.status !== "plan_ready") {
    const card = element("div", "error-card");
    const boundary = data.boundary_outcome || {};
    append(card, element("h3", "", "주문안을 확정할 수 없습니다"));
    if (data.execution?.reason) card.appendChild(element("p", "", data.execution.reason));
    (boundary.questions || []).forEach((q) => card.appendChild(element("p", "", `확인 필요: ${q}`)));
    (boundary.issues || []).forEach((issue) => card.appendChild(element("p", "", `${issue.field_path || "입력"}: ${issue.message}`)));
    if (result?.corrective_action || data.execution?.corrective_action) card.appendChild(element("p", "", `다음 조치: ${result?.corrective_action || data.execution.corrective_action}`));
    host.appendChild(card); return;
  }
  const combo = result.recommended_plan.combination;
  const explanation = data.agent_explanation;
  const hero = element("div", "order-hero");
  append(hero, element("div", "kicker", "RECOMMENDED / BALANCED"), element("h3", "", result.restaurant.name), element("p", "", explanation?.summary || "모든 하드 제약을 통과한 균형 주문안입니다."));
  host.appendChild(hero);
  combo.lines.forEach((line) => {
    const menu = result.restaurant.menu_items.find((item) => item.menu_item_id === line.menu_item_id);
    const row = element("div", "order-line");
    const left = element("div"); append(left, element("strong", "", `${line.quantity} × ${menu?.name || line.menu_item_id}`), element("span", "", `${servings(line.unit_servings_milli)} / 단위`));
    append(row, left, element("strong", "", krw.format(line.line_price_minor))); host.appendChild(row);
  });
  const analysis = result.group_analysis;
  const credit = data.existing_food_credit?.total_credited_servings_milli || 0;
  const grid = element("div", "metric-grid");
  append(grid,
    metric("참석", `${analysis.actual_attendance}명`),
    metric("총 등가 수요", servings(analysis.equivalent_group_servings_milli)),
    metric("기존 음식 반영", `− ${servings(credit)}`),
    metric("최종 목표", servings(combo.target_servings_milli)),
    metric("주문 제공량", servings(combo.total_servings_milli)),
    metric("총액", krw.format(combo.total_cost_minor))
  ); host.appendChild(grid);
  const strategies = [{ plan: result.recommended_plan, label: "균형", selected: true }, ...(result.alternatives || []).map((x) => ({ plan: x.plan, label: x.plan.combination.strategy, selected: false }))];
  const strategyGrid = element("div", "strategy-grid");
  strategies.forEach((item) => {
    const c = item.plan.combination; const card = element("div", `strategy${item.selected ? " selected" : ""}`);
    append(card, element("small", "", item.label), element("strong", "", `${servings(c.target_servings_milli)} · ${krw.format(c.total_cost_minor)}`)); strategyGrid.appendChild(card);
  }); host.appendChild(strategyGrid);
  host.appendChild(element("div", "notice", explanation?.uncertainty_explanation || result.expected_outcome?.important_uncertainties?.join(" · ") || "실제 주문 전 가격과 재고를 다시 확인하세요."));
}

function renderTrace(data) {
  const summary = $("trace-summary"); const host = $("trace-content"); clear(summary); clear(host);
  [data.execution?.status, data.mode, data.boundary_outcome?.status, `${data.pipeline_events?.length || 0} pipeline`, `${data.tool_events?.length || 0} tools`].filter(Boolean).forEach((value) => summary.appendChild(element("span", "", value)));
  const events = [...(data.pipeline_events || []), ...(data.tool_events || [])].sort((a, b) => String(a.occurred_at).localeCompare(String(b.occurred_at)));
  events.forEach((event) => {
    const details = element("details", "trace-item");
    const heading = element("summary");
    const name = event.tool_name ? `${event.event_type} / ${event.tool_name}` : `${event.event_type} / ${event.stage}`;
    append(heading, element("span", "event-dot"), element("span", "trace-name", name), element("span", "trace-time", event.duration_ms === null || event.duration_ms === undefined ? new Date(event.occurred_at).toLocaleTimeString("ko-KR") : `${event.duration_ms}ms`));
    const pre = element("pre", "", JSON.stringify(event, null, 2));
    append(details, heading, pre); host.appendChild(details);
  });
  const boundary = element("details", "trace-item");
  const heading = element("summary"); append(heading, element("span", "event-dot"), element("span", "trace-name", "boundary_outcome / raw JSON"), element("span", "trace-time", "contract"));
  append(boundary, heading, element("pre", "", JSON.stringify(data.boundary_outcome, null, 2))); host.appendChild(boundary);
}

function render(data) {
  $("workspace").hidden = false;
  renderScene(data); renderResult(data); renderTrace(data);
  $("workspace").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function submit(runMode) {
  const file = photoInput.files[0];
  if (!file && !notes.value.trim() && runMode !== "offline_canonical") {
    setStatus("사진 또는 특별사항을 입력해 주세요.", "error"); notes.focus(); return;
  }
  setLoading(true);
  setStatus(runMode === "offline_canonical" ? "준비된 검증 경로를 실행하고 있습니다…" : "현장을 해석하고 검증된 주문 수량을 계산하고 있습니다…", "busy");
  const body = new FormData();
  if (file) body.append("photo", file);
  body.append("notes", notes.value);
  body.append("run_mode", runMode);
  body.append("captured_at", new Date().toISOString());
  body.append("timezone_offset_minutes", String(-new Date().getTimezoneOffset()));
  if (coordinates) { body.append("latitude", String(coordinates.latitude)); body.append("longitude", String(coordinates.longitude)); }
  body.append("location_permission", locationPermission);
  try {
    const response = await fetch("/api/runs", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.reason || `HTTP ${response.status}`);
    render(data);
    setStatus(data.execution?.blocked ? "확인이 필요한 입력입니다." : "주문안 계산이 완료되었습니다.", data.execution?.blocked ? "error" : "success");
  } catch (error) {
    setStatus(`실행 실패: ${error.message}`, "error");
  } finally {
    setLoading(false);
  }
}

photoInput.addEventListener("change", () => {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  const file = photoInput.files[0];
  if (!file) { preview.hidden = true; $("remove-photo").hidden = true; return; }
  previewUrl = URL.createObjectURL(file); preview.src = previewUrl; preview.hidden = false; $("remove-photo").hidden = false;
  setStatus(`${file.name} 준비 완료`, "success");
});

["dragenter", "dragover"].forEach((eventName) => photoDrop.addEventListener(eventName, (event) => {
  event.preventDefault();
  if (!photoInput.disabled) photoDrop.dataset.dragging = "true";
}));

["dragleave", "drop"].forEach((eventName) => photoDrop.addEventListener(eventName, (event) => {
  event.preventDefault();
  delete photoDrop.dataset.dragging;
}));

photoDrop.addEventListener("drop", (event) => {
  if (photoInput.disabled) return;
  const file = [...event.dataTransfer.files].find((item) => item.type.startsWith("image/"));
  if (!file) {
    setStatus("이미지 파일을 놓아 주세요.", "error");
    return;
  }
  const transfer = new DataTransfer();
  transfer.items.add(file);
  photoInput.files = transfer.files;
  photoInput.dispatchEvent(new Event("change"));
});
$("remove-photo").addEventListener("click", () => { photoInput.value = ""; photoInput.dispatchEvent(new Event("change")); });
notes.addEventListener("input", () => { $("char-count").textContent = `${notes.value.length.toLocaleString("ko-KR")} / 5,000`; });
form.addEventListener("submit", (event) => { event.preventDefault(); submit("live"); });
demoButton.addEventListener("click", () => submit("offline_canonical"));
$("copy-json").addEventListener("click", async (event) => { event.preventDefault(); if (latestTerminalJson) { await navigator.clipboard.writeText(JSON.stringify(latestTerminalJson, null, 2)); event.currentTarget.textContent = "복사됨"; } });
$("location-button").addEventListener("click", () => {
  if (!navigator.geolocation) { $("location-label").textContent = "위치 사용 불가"; return; }
  $("location-label").textContent = "위치 확인 중…";
  navigator.geolocation.getCurrentPosition(
    (position) => { coordinates = { latitude: position.coords.latitude, longitude: position.coords.longitude }; locationPermission = "granted"; $("location-label").textContent = "현재 위치 사용 중"; $("location-button").dataset.active = "true"; },
    () => { coordinates = null; locationPermission = "denied"; $("location-label").textContent = "위치 권한 없음 · 특별사항에 장소 입력"; }
  );
});
$("capture-time").textContent = `제출 시각 ${new Date().toLocaleString("ko-KR", { weekday: "short", hour: "2-digit", minute: "2-digit" })}`;
