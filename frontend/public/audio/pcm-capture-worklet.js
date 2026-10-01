// AudioWorklet: microphone (Float32 at the device rate, usually 48 kHz) →
// PCM-16 mono at 16 kHz, posted to the main thread in 20 ms chunks — the
// format the backend forwards straight to Gemini Live.
//
// Downsampling averages each group of input samples (a boxcar low-pass),
// which is enough anti-aliasing for speech.
const TARGET_RATE = 16000;
const CHUNK_SAMPLES = 320; // 20 ms at 16 kHz

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET_RATE; // `sampleRate` is a worklet global
    this.phase = 0;
    this.acc = 0;
    this.count = 0;
    this.out = new Int16Array(CHUNK_SAMPLES);
    this.outIndex = 0;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;
    for (let i = 0; i < input.length; i++) {
      this.acc += input[i];
      this.count += 1;
      this.phase += 1;
      if (this.phase >= this.ratio) {
        this.phase -= this.ratio;
        const s = Math.max(-1, Math.min(1, this.acc / this.count));
        this.out[this.outIndex++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        this.acc = 0;
        this.count = 0;
        if (this.outIndex === CHUNK_SAMPLES) {
          this.port.postMessage(this.out.buffer, [this.out.buffer]);
          this.out = new Int16Array(CHUNK_SAMPLES);
          this.outIndex = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
