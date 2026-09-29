/**
 * Mine Vision-X | Open-Cast Mine Pit Tactical GIS Map Engine
 * Renders topographic quarry benches, switchback haul roads, LoRa repeater towers,
 * active blast zones, and live GPS positions of the entire HEMM fleet with collision detection.
 */

class MineMapEngine {
  constructor(svgId, onVehicleSelect) {
    this.svg = document.getElementById(svgId);
    this.onVehicleSelect = onVehicleSelect;
    this.vehicles = {};
    this.selectedId = "HEMM-101";

    // Center Reference Lat/Lon
    this.refLat = 23.7957;
    this.refLon = 86.4304;

    this.renderBaseMap();
  }

  // Convert GPS (Lat, Lon) to SVG Canvas (X, Y) [1000 x 700]
  gpsToCanvas(lat, lon) {
    const scaleX = 75000;
    const scaleY = 75000;
    const cx = 500;
    const cy = 350;

    const dx = (lon - this.refLon) * scaleX;
    const dy = (this.refLat - lat) * scaleY; // Invert latitude for canvas Y

    return {
      x: Math.max(40, Math.min(960, cx + dx)),
      y: Math.max(40, Math.min(660, cy + dy))
    };
  }

  renderBaseMap() {
    if (!this.svg) return;
    this.svg.innerHTML = `
      <defs>
        <!-- Gradients for Benches & Quarry Depth -->
        <radialGradient id="pitDepthGrad" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#020814" />
          <stop offset="60%" stop-color="#091526" />
          <stop offset="100%" stop-color="#0e1f36" />
        </radialGradient>
        
        <pattern id="gridPattern" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(0, 229, 255, 0.05)" stroke-width="1"/>
        </pattern>

        <!-- Vehicle Glow Filter -->
        <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
        <filter id="glow-red" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      <!-- Background Depth & Grid -->
      <rect width="1000" height="700" fill="url(#pitDepthGrad)" />
      <rect width="1000" height="700" fill="url(#gridPattern)" />

      <!-- CONCENTRIC QUARRY BENCHES (TERRACED PIT) -->
      <!-- Bench 1 (Pit Rim / Crest) -->
      <path d="M 120,90 Q 500,40 880,90 Q 940,350 880,610 Q 500,660 120,610 Q 60,350 120,90 Z" 
            fill="none" stroke="rgba(0, 229, 255, 0.18)" stroke-width="2" stroke-dasharray="6,4" />
      <text x="140" y="80" fill="rgba(0,229,255,0.4)" font-family="Share Tech Mono" font-size="10">BENCH #1 (CREST +310M)</text>

      <!-- Bench 2 -->
      <path d="M 180,140 Q 500,100 820,140 Q 870,350 820,560 Q 500,600 180,560 Q 130,350 180,140 Z" 
            fill="rgba(10, 25, 45, 0.3)" stroke="rgba(0, 229, 255, 0.14)" stroke-width="1.5" />
      
      <!-- Bench 3 -->
      <path d="M 240,190 Q 500,160 760,190 Q 800,350 760,510 Q 500,540 240,510 Q 200,350 240,190 Z" 
            fill="rgba(12, 30, 55, 0.35)" stroke="rgba(0, 229, 255, 0.12)" stroke-width="1.5" />

      <!-- Bench 4 (Deep Pit Floor - Mining Face) -->
      <path d="M 310,240 Q 500,220 690,240 Q 720,350 690,460 Q 500,480 310,460 Q 280,350 310,240 Z" 
            fill="rgba(5, 15, 30, 0.6)" stroke="rgba(0, 229, 255, 0.22)" stroke-width="2" />
      <text x="330" y="235" fill="rgba(0,229,255,0.5)" font-family="Share Tech Mono" font-size="10">BENCH #4 DEEP PIT FACE (+180M)</text>

      <!-- MAIN SWITCHBACK HAUL ROAD RAMPS (SPIRAL ACCESS) -->
      <!-- Spiral Haul Road Curve A & B -->
      <path d="M 140,110 C 350,130 650,150 840,210 C 900,280 880,440 790,520 C 650,620 350,580 220,490 C 170,420 180,300 280,260 C 380,220 620,240 680,310 C 720,380 660,450 500,460"
            fill="none" stroke="rgba(255, 214, 0, 0.35)" stroke-width="18" stroke-linecap="round" stroke-linejoin="round" />
      <!-- Road Centerlines -->
      <path d="M 140,110 C 350,130 650,150 840,210 C 900,280 880,440 790,520 C 650,620 350,580 220,490 C 170,420 180,300 280,260 C 380,220 620,240 680,310 C 720,380 660,450 500,460"
            fill="none" stroke="#ffd600" stroke-width="2" stroke-dasharray="8,8" />

      <!-- MINING FACILITY INFRASTRUCTURE -->
      <!-- 1. Primary Crusher & Processing Plant (Top East) -->
      <g transform="translate(820, 70)">
        <rect x="-35" y="-20" width="70" height="40" fill="rgba(41, 121, 255, 0.25)" stroke="#2979ff" stroke-width="1.5" rx="3"/>
        <text x="0" y="-4" fill="#fff" font-family="Rajdhani" font-size="11" font-weight="700" text-anchor="middle">PRIMARY CRUSHER</text>
        <text x="0" y="10" fill="rgba(255,255,255,0.7)" font-family="Share Tech Mono" font-size="8" text-anchor="middle">UNLOAD HOPPER #1</text>
      </g>

      <!-- 2. Overburden Dump Yard Alpha (Top West) -->
      <g transform="translate(140, 70)">
        <polygon points="-40,-15 40,-15 30,20 -30,20" fill="rgba(255, 145, 0, 0.2)" stroke="#ff9100" stroke-width="1.5" stroke-dasharray="4,2"/>
        <text x="0" y="3" fill="#ff9100" font-family="Rajdhani" font-size="10" font-weight="700" text-anchor="middle">DUMP YARD ALPHA</text>
      </g>

      <!-- 3. Active Blast Danger Zone (South Face - Bench 6) -->
      <g transform="translate(480, 590)">
        <rect x="-80" y="-25" width="160" height="50" fill="rgba(255, 23, 68, 0.2)" stroke="#ff1744" stroke-width="2" stroke-dasharray="6,4" rx="4"/>
        <text x="0" y="-5" fill="#ff1744" font-family="Orbitron" font-size="10" font-weight="700" text-anchor="middle">⚠️ RESTRICTED BLAST ZONE</text>
        <text x="0" y="12" fill="rgba(255,255,255,0.7)" font-family="Share Tech Mono" font-size="8" text-anchor="middle">ACTIVE DRILLING &bull; NO ENTRY</text>
      </g>

      <!-- 4. Central Office Surveillance HQ & LoRa Tower Base (West Rim) -->
      <g transform="translate(60, 350)">
        <rect x="-35" y="-30" width="70" height="60" fill="rgba(0, 229, 255, 0.15)" stroke="#00e5ff" stroke-width="2" rx="4"/>
        <circle cx="0" cy="-8" r="8" fill="none" stroke="#00e5ff" stroke-width="1.5"/>
        <line x1="0" y1="-16" x2="0" y2="12" stroke="#00e5ff" stroke-width="2"/>
        <text x="0" y="24" fill="#00e5ff" font-family="Rajdhani" font-size="9" font-weight="700" text-anchor="middle">CENTRAL HQ</text>
        <!-- Antenna Wave Pulses -->
        <circle cx="0" cy="-16" r="14" fill="none" stroke="rgba(0,229,255,0.4)" stroke-dasharray="3,3" />
        <circle cx="0" cy="-16" r="24" fill="none" stroke="rgba(0,229,255,0.2)" stroke-dasharray="4,4" />
      </g>

      <!-- LoRa Repeater Towers around pit rim -->
      <g transform="translate(480, 30)">
        <circle cx="0" cy="0" r="5" fill="#d500f9" />
        <circle cx="0" cy="0" r="18" fill="none" stroke="rgba(213,0,249,0.3)" stroke-dasharray="3,3" />
        <text x="0" y="14" fill="#d500f9" font-family="Share Tech Mono" font-size="8" text-anchor="middle">GW-TOWER-NORTH</text>
      </g>

      <g transform="translate(940, 380)">
        <circle cx="0" cy="0" r="5" fill="#d500f9" />
        <circle cx="0" cy="0" r="18" fill="none" stroke="rgba(213,0,249,0.3)" stroke-dasharray="3,3" />
        <text x="0" y="14" fill="#d500f9" font-family="Share Tech Mono" font-size="8" text-anchor="middle">GW-TOWER-SOUTH</text>
      </g>

      <g transform="translate(500, 370)">
        <circle cx="0" cy="0" r="4" fill="#d500f9" />
        <text x="0" y="-8" fill="#d500f9" font-family="Share Tech Mono" font-size="8" text-anchor="middle">GW-TOWER-PIT</text>
      </g>

      <!-- Dynamic Layer: Collision Warning Chords -->
      <g id="map-collision-chords"></g>

      <!-- Dynamic Layer: Vehicle Markers -->
      <g id="map-vehicles-group"></g>
    `;

    this.vehiclesGroup = document.getElementById("map-vehicles-group");
    this.collisionGroup = document.getElementById("map-collision-chords");
  }

  updateFleet(vehicles, selectedId) {
    this.vehicles = vehicles || {};
    this.selectedId = selectedId || "HEMM-101";

    if (!this.vehiclesGroup) return;

    // 1. Render Collision Chords between vehicles in proximity (<40m)
    let chordsHtml = "";
    const vList = Object.values(this.vehicles);
    for (let i = 0; i < vList.length; i++) {
      for (let j = i + 1; j < vList.length; j++) {
        const vA = vList[i];
        const vB = vList[j];
        if (!vA.gps || !vB.gps) continue;

        const posA = this.gpsToCanvas(vA.gps.latitude, vA.gps.longitude);
        const posB = this.gpsToCanvas(vB.gps.latitude, vB.gps.longitude);

        // Calculate distance on canvas
        const dist = Math.hypot(posA.x - posB.x, posA.y - posB.y);
        if (dist < 80) { // Danger proximity
          chordsHtml += `
            <line x1="${posA.x}" y1="${posA.y}" x2="${posB.x}" y2="${posB.y}" 
                  stroke="#ff1744" stroke-width="2" stroke-dasharray="4,4" filter="url(#glow-red)" />
            <circle cx="${(posA.x + posB.x)/2}" cy="${(posA.y + posB.y)/2}" r="12" fill="#ff1744" opacity="0.8" />
            <text x="${(posA.x + posB.x)/2}" y="${(posA.y + posB.y)/2 + 3}" fill="#fff" font-family="Rajdhani" font-size="9" font-weight="700" text-anchor="middle">⚠️ PROX</text>
          `;
        }
      }
    }
    if (this.collisionGroup) {
      this.collisionGroup.innerHTML = chordsHtml;
    }

    // 2. Render Vehicle Nodes
    let vehiclesHtml = "";
    vList.forEach(v => {
      if (!v.gps) return;
      const pos = this.gpsToCanvas(v.gps.latitude, v.gps.longitude);
      const isSelected = (v.id === this.selectedId);
      const heading = v.gps.heading_deg || 0;
      const speed = v.gps.speed_kmh || 0;

      // Color coding by vehicle category
      let col = "#ffd600"; // Haul truck
      if (v.id.includes("204")) col = "#00e5ff"; // Shovel
      else if (v.id.includes("305") || v.id.includes("408")) col = "#ff9100"; // Loader/Dozer
      else if (v.id.includes("LMV")) col = "#00e676"; // Patrol 4x4

      if (v.status === "EMERGENCY_STOPPED") col = "#ff1744";

      // Collision safety circle
      const safetyRing = isSelected ? `
        <circle cx="${pos.x}" cy="${pos.y}" r="26" fill="rgba(0, 229, 255, 0.12)" stroke="#00e5ff" stroke-width="1.5" stroke-dasharray="4,4" />
      ` : "";

      vehiclesHtml += `
        <g class="vehicle-marker ${isSelected ? 'selected-node' : ''}" 
           style="cursor: pointer;" 
           onclick="window.selectVehicle('${v.id}')">
          
          ${safetyRing}

          <!-- Direction Heading Arrow -->
          <g transform="translate(${pos.x}, ${pos.y}) rotate(${heading})">
            <polygon points="0,-16 6,0 0,-4 -6,0" fill="${col}" filter="url(#glow-cyan)" />
          </g>

          <!-- Core Vehicle Icon Circle -->
          <circle cx="${pos.x}" cy="${pos.y}" r="${isSelected ? 10 : 8}" fill="${col}" stroke="#000" stroke-width="1.5" />
          
          <!-- Label Tag -->
          <g transform="translate(${pos.x + 14}, ${pos.y + 4})">
            <rect x="-2" y="-12" width="76" height="15" fill="rgba(5, 12, 22, 0.85)" stroke="${isSelected ? '#00e5ff' : 'rgba(255,255,255,0.2)'}" stroke-width="1" rx="2" />
            <text x="2" y="-1" fill="#fff" font-family="Rajdhani" font-size="10" font-weight="700">${v.id} &bull; ${speed.toFixed(0)}k</text>
          </g>
        </g>
      `;
    });

    this.vehiclesGroup.innerHTML = vehiclesHtml;
  }
}
