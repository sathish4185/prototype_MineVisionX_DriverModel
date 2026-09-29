/**
 * Mine Vision-X | 77 GHz mmWave Polar Radar Visualizer
 * Sweeps a 120° front detection cone with dynamic target plotting and range rings.
 */

class RadarScopeVisualizer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.sweepAngle = -60;
    this.sweepSpeed = 2.4; // deg per frame
    this.sweepDirection = 1;
    this.targets = [];
    this.maxRangeMeters = 80;

    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  setTargets(targets, maxRange = 80) {
    this.targets = targets || [];
    this.maxRangeMeters = maxRange;
  }

  animate() {
    if (!this.ctx) return;
    const w = this.canvas.width;
    const h = this.canvas.height;
    const ox = w / 2;
    const oy = h - 15;
    const radius = h - 25;

    // Clear background
    this.ctx.fillStyle = '#02060d';
    this.ctx.fillRect(0, 0, w, h);

    // Draw Range Rings (20m, 40m, 60m, 80m)
    const ringSteps = [0.25, 0.5, 0.75, 1.0];
    this.ctx.strokeStyle = 'rgba(0, 229, 255, 0.2)';
    this.ctx.lineWidth = 1;

    ringSteps.forEach(ratio => {
      const r = radius * ratio;
      this.ctx.beginPath();
      this.ctx.arc(ox, oy, r, -Math.PI * 0.85, -Math.PI * 0.15);
      this.ctx.stroke();

      // Range text
      this.ctx.fillStyle = 'rgba(0, 229, 255, 0.45)';
      this.ctx.font = '9px "Share Tech Mono", monospace';
      this.ctx.fillText(`${Math.round(this.maxRangeMeters * ratio)}m`, ox + 4, oy - r + 10);
    });

    // Draw Angle Raylines (-60°, -30°, 0°, +30°, +60°)
    const angles = [-60, -30, 0, 30, 60];
    angles.forEach(deg => {
      const rad = (deg - 90) * (Math.PI / 180);
      const ex = ox + radius * Math.cos(rad);
      const ey = oy + radius * Math.sin(rad);

      this.ctx.beginPath();
      this.ctx.moveTo(ox, oy);
      this.ctx.lineTo(ex, ey);
      this.ctx.strokeStyle = deg === 0 ? 'rgba(0, 229, 255, 0.35)' : 'rgba(0, 229, 255, 0.12)';
      this.ctx.stroke();
    });

    // Update & Draw Radar Sweep Line
    this.sweepAngle += this.sweepSpeed * this.sweepDirection;
    if (this.sweepAngle >= 60) {
      this.sweepDirection = -1;
    } else if (this.sweepAngle <= -60) {
      this.sweepDirection = 1;
    }

    const sweepRad = (this.sweepAngle - 90) * (Math.PI / 180);
    const sweepX = ox + radius * Math.cos(sweepRad);
    const sweepY = oy + radius * Math.sin(sweepRad);

    // Glowing beam
    const gradient = this.ctx.createRadialGradient(ox, oy, 10, ox, oy, radius);
    gradient.addColorStop(0, 'rgba(0, 229, 255, 0.3)');
    gradient.addColorStop(1, 'rgba(0, 230, 118, 0.05)');

    this.ctx.beginPath();
    this.ctx.moveTo(ox, oy);
    this.ctx.arc(ox, oy, radius, sweepRad - 0.15, sweepRad + 0.15);
    this.ctx.closePath();
    this.ctx.fillStyle = gradient;
    this.ctx.fill();

    this.ctx.beginPath();
    this.ctx.moveTo(ox, oy);
    this.ctx.lineTo(sweepX, sweepY);
    this.ctx.strokeStyle = '#00e5ff';
    this.ctx.lineWidth = 2;
    this.ctx.stroke();

    // Plot Targets
    this.targets.forEach(tgt => {
      const dist = tgt.dist_m || 30;
      const angle = tgt.angle_deg || 0;
      const r = (dist / this.maxRangeMeters) * radius;
      const rad = (angle - 90) * (Math.PI / 180);
      const tx = ox + r * Math.cos(rad);
      const ty = oy + r * Math.sin(rad);

      // Color based on distance
      let col = '#00e676';
      if (dist < 20) col = '#ff1744';
      else if (dist < 40) col = '#ffd600';

      // Outer blip ring
      this.ctx.beginPath();
      this.ctx.arc(tx, ty, 6, 0, Math.PI * 2);
      this.ctx.strokeStyle = col;
      this.ctx.lineWidth = 1.5;
      this.ctx.stroke();

      // Inner dot
      this.ctx.beginPath();
      this.ctx.arc(tx, ty, 3, 0, Math.PI * 2);
      this.ctx.fillStyle = col;
      this.ctx.fill();

      // Label
      this.ctx.fillStyle = '#fff';
      this.ctx.font = '9px "Rajdhani", sans-serif';
      this.ctx.fillText(`${dist.toFixed(1)}m`, tx + 8, ty + 3);
    });

    // Radar Center Origin Dot (Vehicle Radar Transceiver on front bumper)
    this.ctx.beginPath();
    this.ctx.arc(ox, oy, 4, 0, Math.PI * 2);
    this.ctx.fillStyle = '#00e5ff';
    this.ctx.fill();

    requestAnimationFrame(this.animate);
  }
}
