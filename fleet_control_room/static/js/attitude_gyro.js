/**
 * Mine Vision-X | 3D Attitude & Rollover Gyroscope (MMA7660 / Jetson IMU)
 * Uses Three.js to render an authentic 3D wireframe Heavy Mining Truck
 * that tilts in real-time with vehicle pitch (slope) and roll.
 */

class AttitudeGyroVisualizer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;

    this.pitch = 0;
    this.roll = 0;
    this.initThree();
  }

  initThree() {
    if (typeof THREE === 'undefined') {
      console.warn("Three.js not loaded, fallback will be used");
      return;
    }

    const w = this.container.clientWidth || 140;
    const h = this.container.clientHeight || 100;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);
    this.camera.position.set(0, 5, 12);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(w, h);
    this.renderer.setClearColor(0x02060d, 0.8);
    this.container.appendChild(this.renderer.domElement);

    // Ambient & directional lighting
    const amb = new THREE.AmbientLight(0xffffff, 0.7);
    this.scene.add(amb);
    const dir = new THREE.DirectionalLight(0x00e5ff, 1.2);
    dir.position.set(5, 10, 7);
    this.scene.add(dir);

    // Build 3D Heavy Mining Haul Truck Model
    this.truckGroup = new THREE.Group();

    // Chassis
    const chassisGeo = new THREE.BoxGeometry(3.6, 1.0, 6.0);
    const chassisMat = new THREE.MeshStandardMaterial({
      color: 0x1a2638,
      wireframe: false,
      roughness: 0.4
    });
    const chassis = new THREE.Mesh(chassisGeo, chassisMat);
    chassis.position.y = 1.0;
    this.truckGroup.add(chassis);

    // Yellow Dump Body (Quarry Tipper)
    const dumpGeo = new THREE.BoxGeometry(4.0, 1.8, 5.2);
    const dumpMat = new THREE.MeshStandardMaterial({
      color: 0xffaa00,
      metalness: 0.3,
      roughness: 0.3
    });
    const dump = new THREE.Mesh(dumpGeo, dumpMat);
    dump.position.set(0, 2.2, -0.4);
    this.truckGroup.add(dump);

    // Cab / Cockpit
    const cabGeo = new THREE.BoxGeometry(1.6, 1.4, 2.0);
    const cabMat = new THREE.MeshStandardMaterial({
      color: 0xe0e6ed,
      roughness: 0.2
    });
    const cab = new THREE.Mesh(cabGeo, cabMat);
    cab.position.set(-1.0, 2.3, 1.8);
    this.truckGroup.add(cab);

    // Big Giant Mining Wheels (4 corners)
    const wheelGeo = new THREE.CylinderGeometry(0.9, 0.9, 0.7, 16);
    const wheelMat = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.8 });
    wheelGeo.rotateZ(Math.PI / 2);

    const positions = [
      [-1.9, 0.9, 2.0],
      [1.9, 0.9, 2.0],
      [-1.9, 0.9, -2.0],
      [1.9, 0.9, -2.0]
    ];

    positions.forEach(pos => {
      const wheel = new THREE.Mesh(wheelGeo, wheelMat);
      wheel.position.set(...pos);
      this.truckGroup.add(wheel);
    });

    // Wireframe Cage for cyber HUD appearance
    const wireMat = new THREE.LineBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.6 });
    const wireGeo = new THREE.WireframeGeometry(dumpGeo);
    const wire = new THREE.LineSegments(wireGeo, wireMat);
    wire.position.copy(dump.position);
    this.truckGroup.add(wire);

    // Artificial Horizon Ring
    const ringGeo = new THREE.RingGeometry(5.2, 5.4, 32);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x00e5ff, side: THREE.DoubleSide, transparent: true, opacity: 0.4 });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.9;
    this.scene.add(ring);

    this.scene.add(this.truckGroup);

    this.render = this.render.bind(this);
    requestAnimationFrame(this.render);
  }

  updateAttitude(pitchDeg, rollDeg) {
    this.pitch = pitchDeg || 0;
    this.roll = rollDeg || 0;

    if (this.truckGroup) {
      // Convert degrees to radians
      // Pitch is X rotation, Roll is Z rotation
      const pRad = (this.pitch * Math.PI) / 180;
      const rRad = (this.roll * Math.PI) / 180;

      this.truckGroup.rotation.x = -pRad;
      this.truckGroup.rotation.z = -rRad;
    }
  }

  render() {
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
    requestAnimationFrame(this.render);
  }
}
