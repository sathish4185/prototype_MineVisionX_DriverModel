/**
 * Mine Vision-X | Web Audio Alert Synthesizer
 * Generates industrial sound cues for security surveillance without external audio files.
 */

class ControlRoomAudio {
  constructor() {
    this.ctx = null;
    this.isMuted = false;
  }

  init() {
    if (!this.ctx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        this.ctx = new AudioContext();
      }
    }
  }

  playBeep(freq = 880, duration = 0.15, type = 'sine') {
    if (this.isMuted) return;
    this.init();
    if (!this.ctx) return;

    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, this.ctx.currentTime);
      gain.gain.setValueAtTime(0.15, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + duration);

      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start();
      osc.stop(this.ctx.currentTime + duration);
    } catch (e) {
      console.warn("Audio synth:", e);
    }
  }

  playCaution() {
    this.playBeep(620, 0.1, 'triangle');
    setTimeout(() => this.playBeep(840, 0.12, 'triangle'), 120);
  }

  playCriticalAlarm() {
    this.playBeep(980, 0.15, 'sawtooth');
    setTimeout(() => this.playBeep(650, 0.2, 'sawtooth'), 160);
  }

  playDispatchChime() {
    this.playBeep(523.25, 0.12, 'sine');
    setTimeout(() => this.playBeep(659.25, 0.12, 'sine'), 130);
    setTimeout(() => this.playBeep(783.99, 0.25, 'sine'), 260);
  }

  toggleMute() {
    this.isMuted = !this.isMuted;
    return this.isMuted;
  }
}

window.soundFx = new ControlRoomAudio();
