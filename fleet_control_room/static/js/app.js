/**
 * Mine Vision-X | Central Fleet Control Room Application Orchestrator
 * High-performance state synchronization, tele-actions, and surveillance management.
 */

let selectedVehicleId = "HEMM-101";
let currentCamTab = "optical";
let currentViewMode = "wall";
let radarVisualizer = null;
let attitudeGyro = null;
let mineMap = null;
let lastAlertState = "green";

// Initialize on page load
window.addEventListener("DOMContentLoaded", () => {
  // Initialize Sub-visualizers
  radarVisualizer = new RadarScopeVisualizer("radar-canvas");
  attitudeGyro = new AttitudeGyroVisualizer("gyro-3d-box");
  mineMap = new MineMapEngine("mine-map-svg", selectVehicle);

  // Start UTC Clock
  setInterval(updateClock, 1000);
  updateClock();

  // Initial Fleet Poll & start 10 Hz loop
  pollFleetData();
  setInterval(pollFleetData, 100);

  // Poll Incidents every 1.5s
  pollIncidents();
  setInterval(pollIncidents, 1500);
});

// Update UTC Clock
function updateClock() {
  const now = new Date();
  const utcStr = now.toUTCString().split(" ")[4] + " UTC";
  const el = document.getElementById("live-clock");
  if (el) el.innerText = utcStr;
}

// Select Active Vehicle for Inspection
window.selectVehicle = function(vid) {
  selectedVehicleId = vid;
  const title = document.getElementById("cam-panel-title");
  if (title) title.innerHTML = `LIVE SURVEILLANCE FEED &bull; ${vid}`;

  const telemTitle = document.getElementById("telemetry-panel-title");
  if (telemTitle) telemTitle.innerHTML = `VEHICLE SENSOR FUSION &bull; ${vid}`;

  // Update Live Video Source
  updateVideoSource();
};

// Update Video Source based on current vehicle & tab
function updateVideoSource() {
  const img = document.getElementById("live-stream-img");
  const quad = document.getElementById("quad-grid");
  
  if (currentCamTab === "quad") {
    if (img) img.style.display = "none";
    if (quad) quad.style.display = "grid";
  } else {
    if (quad) quad.style.display = "none";
    if (img) {
      img.style.display = "block";
      img.src = `/video_feed/${selectedVehicleId}?tab=${currentCamTab}&t=${Date.now()}`;
    }
  }
}

// Camera Tabs
function setCamTab(tab) {
  currentCamTab = tab;
  document.querySelectorAll(".cam-tab").forEach(b => b.classList.remove("active"));
  const btn = document.getElementById(`tab-${tab}`);
  if (btn) btn.classList.add("active");

  const filterImg = document.getElementById("live-stream-img");
  if (tab === "thermal") {
    document.getElementById("hud-cam-type").innerText = "SENSOR: THERMAL IR LWIR (FLIR IRONBOW)";
  } else {
    document.getElementById("hud-cam-type").innerText = "SENSOR: SONY IMX / OV5647 CSI";
  }

  updateVideoSource();
}

// View Mode Toggle (Command Wall vs Full Map)
function setViewMode(mode) {
  currentViewMode = mode;
  document.querySelectorAll(".btn-ctrl-mode").forEach(b => b.classList.remove("active"));
  const btn = document.getElementById(`btn-mode-${mode}`);
  if (btn) btn.classList.add("active");

  const grid = document.getElementById("main-grid");
  if (mode === "map") {
    grid.style.gridTemplateColumns = "0.7fr 1.8fr 0.8fr";
  } else {
    grid.style.gridTemplateColumns = "1.15fr 1.35fr 0.95fr";
  }
}

// Main Ingestion Poller
async function pollFleetData() {
  try {
    const resp = await fetch("/api/fleet");
    if (!resp.ok) return;
    const data = await resp.json();

    const vehicles = data.vehicles || {};
    const activeCount = Object.keys(vehicles).length;
    document.getElementById("val-active-count").innerText = `${activeCount} HEMM`;

    // Fog protocol
    const fogEl = document.getElementById("val-fog-protocol");
    if (fogEl) {
      fogEl.innerText = data.global_fog_mode ? "ACTIVE (15 KM/H)" : "STANDBY";
      fogEl.className = data.global_fog_mode ? "value val-amber" : "value";
      document.getElementById("btn-fog-sub").innerText = data.global_fog_mode ? "Deactivate Mode" : "Activate Safe Mode";
    }

    // Render Fleet Selector Pills
    renderFleetPills(vehicles);

    // Update Selected Vehicle Telemetry
    const v = vehicles[selectedVehicleId] || vehicles["HEMM-101"];
    if (v) {
      updateVehicleTelemetry(v);
    }

    // Update GIS Map Engine
    if (mineMap) {
      mineMap.updateFleet(vehicles, selectedVehicleId);
    }

  } catch (err) {
    console.error("Poll error:", err);
  }
}

// Render Fleet Selector Pills
function renderFleetPills(vehicles) {
  const container = document.getElementById("fleet-pills-container");
  if (!container) return;

  let html = "";
  Object.values(vehicles).forEach(v => {
    const isSel = (v.id === selectedVehicleId);
    let statusClass = "";
    if (v.radar && v.radar.alert_level === "CRITICAL") statusClass = "status-danger";
    else if (v.radar && v.radar.alert_level === "CAUTION") statusClass = "status-caution";

    html += `
      <div class="vehicle-pill ${isSel ? 'active' : ''} ${statusClass}" onclick="selectVehicle('${v.id}')">
        <span class="v-status-dot"></span>
        <span class="v-id">${v.id}</span>
        <span class="v-type">${v.powertrain ? v.powertrain.speed_kmh.toFixed(0) : 0} km/h &bull; ${v.model ? v.model.split(" ")[0] : ""}</span>
      </div>
    `;
  });
  container.innerHTML = html;
}

// Update Selected Vehicle HUD & Diagnostics
function updateVehicleTelemetry(v) {
  // Powertrain & speed
  if (v.powertrain) {
    document.getElementById("val-speed").innerText = v.powertrain.speed_kmh.toFixed(1);
    document.getElementById("val-rpm").innerText = v.powertrain.rpm.toFixed(0);
    document.getElementById("val-load").innerText = `${v.powertrain.motor_load_pct}%`;
    document.getElementById("hud-speed-readout").innerText = `SPEED: ${v.powertrain.speed_kmh.toFixed(1)} km/h`;
  }

  // Ultrasonic Proximity
  if (v.ultrasonic) {
    document.getElementById("val-ultrasonic").innerText = v.ultrasonic.distance_cm.toFixed(1);
  }

  // Radar Readouts & Visualizer
  if (v.radar) {
    document.getElementById("radar-dist-val").innerText = `${v.radar.distance_m.toFixed(1)} m`;
    document.getElementById("radar-relspd-val").innerText = `${v.radar.rel_speed_kmh} km/h`;
    document.getElementById("hud-distance-readout").innerText = `RADAR RANGE: ${v.radar.distance_m.toFixed(1)} m`;

    const rTag = document.getElementById("radar-alert-tag");
    if (rTag) {
      rTag.innerText = v.radar.alert_level;
      rTag.className = `radar-tag val-${v.radar.alert_level === 'CRITICAL' ? 'red' : v.radar.alert_level === 'CAUTION' ? 'amber' : 'green'}`;
    }

    if (radarVisualizer) {
      radarVisualizer.setTargets(v.radar.targets || [{ dist_m: v.radar.distance_m, angle_deg: 2.5 }]);
    }

    // Audio cue on danger change
    if (v.radar.alert_level === "CRITICAL" && lastAlertState !== "CRITICAL") {
      window.soundFx.playCriticalAlarm();
    } else if (v.radar.alert_level === "CAUTION" && lastAlertState === "CLEAR") {
      window.soundFx.playCaution();
    }
    lastAlertState = v.radar.alert_level;
  }

  // IMU Attitude Readouts & 3D Gyro
  if (v.imu) {
    document.getElementById("val-pitch").innerText = `${v.imu.pitch_deg > 0 ? '+' : ''}${v.imu.pitch_deg.toFixed(1)}°`;
    document.getElementById("val-roll").innerText = `${v.imu.roll_deg > 0 ? '+' : ''}${v.imu.roll_deg.toFixed(1)}°`;
    document.getElementById("val-ay").innerText = `${v.imu.ay > 0 ? '+' : ''}${v.imu.ay.toFixed(2)} g`;
    document.getElementById("val-az").innerText = `${v.imu.az > 0 ? '+' : ''}${v.imu.az.toFixed(2)} g`;

    const imuTag = document.getElementById("imu-risk-tag");
    if (imuTag) {
      imuTag.innerText = v.imu.rollover_risk;
      imuTag.className = `imu-tag val-${v.imu.rollover_risk.includes('CRITICAL') ? 'red' : v.imu.rollover_risk.includes('CAUTION') ? 'amber' : 'green'}`;
    }

    // Update 3D Gyro
    if (attitudeGyro) {
      attitudeGyro.updateAttitude(v.imu.pitch_deg, v.imu.roll_deg);
    }

    // Slope bar
    const slopeDeg = Math.abs(v.imu.pitch_deg);
    const pct = Math.min(100, Math.round((slopeDeg / 15.0) * 100));
    document.getElementById("slope-bar-fill").style.width = `${pct}%`;
    document.getElementById("slope-text").innerText = `${slopeDeg.toFixed(1)}° (Safe limit: 12.0°)`;
  }

  // GPS HUD
  if (v.gps) {
    document.getElementById("hud-lat").innerText = `${v.gps.latitude.toFixed(6)}° N`;
    document.getElementById("hud-lon").innerText = `${v.gps.longitude.toFixed(6)}° E`;
    document.getElementById("hud-alt").innerText = `${v.gps.altitude_m.toFixed(1)} m`;
    document.getElementById("map-sats-count").innerText = `${v.gps.satellites} SATS`;
    document.getElementById("map-hdop-val").innerText = `HDOP: ${v.gps.hdop.toFixed(2)}`;
  }

  // Wireless Transmutation Link Health
  if (v.connection) {
    document.getElementById("val-rssi").innerText = `${v.connection.rssi_dbm} dBm`;
    document.getElementById("val-snr").innerText = `+${v.connection.snr_db} dB`;
    document.getElementById("val-pdr").innerText = `${v.connection.pdr_pct}%`;
    document.getElementById("val-latency").innerText = `${v.connection.latency_ms} ms`;
    document.getElementById("val-gateway-node").innerText = v.connection.gateway || "GW-TOWER-NORTH";

    const linkTypeEl = document.getElementById("hud-link-type");
    if (linkTypeEl) {
      linkTypeEl.innerText = v.connection.is_physical_bridge 
        ? "LINK: PHYSICAL VEHICLE (LIVE CSI/I2C)" 
        : `LINK: ${v.connection.type} (TRANSMUTED)`;
    }
  }

  // Safety Status
  const healthBadge = document.getElementById("vehicle-health-badge");
  if (healthBadge) {
    if (v.status === "EMERGENCY_STOPPED") {
      healthBadge.innerText = "STATUS: E-STOP ENGAGED";
      healthBadge.className = "status-pill-small val-red";
    } else {
      healthBadge.innerText = `STATUS: ${v.status}`;
      healthBadge.className = "status-pill-small";
    }
  }
}

// Poll Incident Blackbox Log
async function pollIncidents() {
  try {
    const resp = await fetch("/api/incidents");
    if (!resp.ok) return;
    const data = await resp.json();
    const container = document.getElementById("incidents-container");
    if (!container) return;

    let html = "";
    (data.incidents || []).slice(0, 8).forEach(inc => {
      const sevClass = inc.severity === "CRITICAL" ? "sev-critical" : inc.severity === "WARNING" ? "sev-warning" : "sev-info";
      html += `
        <div class="incident-row ${sevClass}">
          <div class="inc-left">
            <span class="inc-time">${inc.timestamp}</span>
            <span class="inc-vid">[${inc.vehicle_id}]</span>
            <span class="inc-desc">${inc.details}</span>
          </div>
          <button class="btn-ack" onclick="acknowledgeIncident('${inc.id}')">${inc.acknowledged ? 'ACKED' : 'ACK'}</button>
        </div>
      `;
    });
    container.innerHTML = html;
  } catch (err) {
    console.error("Incident fetch:", err);
  }
}

// Acknowledge Incident
async function acknowledgeIncident(id) {
  try {
    await fetch("/api/incidents/acknowledge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    pollIncidents();
  } catch (e) {
    console.error(e);
  }
}

// ================= DISPATCHER TELE-ACTIONS =================

// Remote Emergency Stop
async function triggerRemoteEstop() {
  if (!confirm(`CONFIRM REMOTE E-STOP: Cut propulsion power immediately to ${selectedVehicleId}?`)) return;

  try {
    window.soundFx.playCriticalAlarm();
    const resp = await fetch("/api/control/estop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vehicle_id: selectedVehicleId })
    });
    const res = await resp.json();
    alert(`🚨 EMERGENCY STOP EXECUTED ON ${selectedVehicleId}!\nPowertrain speed set to 0.0 km/h.`);
    pollFleetData();
  } catch (err) {
    alert("E-STOP transmission failure: " + err);
  }
}

// Remote Horn / Siren
async function triggerRemoteHorn() {
  try {
    window.soundFx.playCaution();
    const resp = await fetch("/api/control/horn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vehicle_id: selectedVehicleId, duration: 3.0 })
    });
    alert(`📢 Acoustic fog siren sounded on ${selectedVehicleId} for 3.0 seconds.`);
  } catch (err) {
    console.error(err);
  }
}

// Broadcast Cabin Message
async function sendCabinMessage() {
  const input = document.getElementById("txt-cabin-msg");
  const msg = input.value.trim();
  if (!msg) return;

  try {
    window.soundFx.playDispatchChime();
    await fetch("/api/control/cabin_message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vehicle_id: selectedVehicleId, message: msg })
    });
    alert(`📡 Transmuted to ${selectedVehicleId} In-Cabin Display:\n"${msg}"`);
  } catch (err) {
    alert("Cabin message error: " + err);
  }
}

// Toggle Global Mine Fog Protocol
async function toggleGlobalFogMode() {
  try {
    window.soundFx.playCaution();
    const resp = await fetch("/api/control/fog_mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const res = await resp.json();
    pollFleetData();
  } catch (err) {
    console.error(err);
  }
}

// Camera Filters & Controls
function toggleAiBoxes(enabled) {
  const overlay = document.getElementById("ai-overlay");
  if (overlay) overlay.style.display = enabled ? "block" : "none";
}

function toggleFogFilter(enabled) {
  const img = document.getElementById("live-stream-img");
  if (img) {
    if (enabled) img.classList.add("fog-filtered");
    else img.classList.remove("fog-filtered");
  }
}

function takeSnapshot() {
  const img = document.getElementById("live-stream-img");
  if (!img) return;
  const link = document.createElement("a");
  link.href = img.src;
  link.download = `MINE_VISION_X_${selectedVehicleId}_${Date.now()}.jpg`;
  link.click();
}

function toggleFullscreen() {
  const vp = document.getElementById("video-viewport");
  if (!document.fullscreenElement) {
    vp.requestFullscreen().catch(err => alert("Fullscreen error: " + err));
  } else {
    document.exitFullscreen();
  }
}

function toggleAudio() {
  const muted = window.soundFx.toggleMute();
  document.getElementById("audio-icon").innerText = muted ? "🔇" : "🔊";
}

// Bridge Config Modal
function openBridgeModal() {
  document.getElementById("modal-bridge").style.display = "flex";
}

function closeBridgeModal() {
  document.getElementById("modal-bridge").style.display = "none";
}

async function saveBridgeUrl() {
  const url = document.getElementById("bridge-url-input").value.trim();
  if (!url) return;

  try {
    const resp = await fetch("/api/settings/bridge_url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });
    const res = await resp.json();
    document.getElementById("modal-bridge-status").innerText = "Linked: " + res.bridge_url;
    setTimeout(closeBridgeModal, 800);
  } catch (err) {
    alert("Bridge update error: " + err);
  }
}
