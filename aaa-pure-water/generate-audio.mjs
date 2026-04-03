/**
 * Generate audio assets for AAA Pure Water video ads.
 * Creates WAV files programmatically using raw PCM synthesis.
 */

import { writeFileSync } from 'fs';

const SAMPLE_RATE = 44100;
const CHANNELS = 1;
const BITS_PER_SAMPLE = 16;

function createWavBuffer(samples) {
  const dataSize = samples.length * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  
  // RIFF header
  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write('WAVE', 8);
  
  // fmt chunk
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20); // PCM
  buffer.writeUInt16LE(CHANNELS, 22);
  buffer.writeUInt32LE(SAMPLE_RATE, 24);
  buffer.writeUInt32LE(SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE / 8, 28);
  buffer.writeUInt16LE(CHANNELS * BITS_PER_SAMPLE / 8, 32);
  buffer.writeUInt16LE(BITS_PER_SAMPLE, 34);
  
  // data chunk
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataSize, 40);
  
  for (let i = 0; i < samples.length; i++) {
    const val = Math.max(-1, Math.min(1, samples[i]));
    buffer.writeInt16LE(Math.round(val * 32767), 44 + i * 2);
  }
  
  return buffer;
}

function generateSamples(durationSec, fn) {
  const length = Math.floor(SAMPLE_RATE * durationSec);
  const samples = new Float64Array(length);
  for (let i = 0; i < length; i++) {
    const t = i / SAMPLE_RATE;
    samples[i] = fn(t, i, length);
  }
  return samples;
}

// --- 1. Ominous Drone (15 seconds) ---
// Low frequency drone with subtle modulation
const drone = generateSamples(15, (t) => {
  const f1 = 55; // Low A
  const f2 = 58; // Slightly detuned
  const f3 = 82.5; // Low E
  const lfo = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(2 * Math.PI * 0.15 * t));
  const sig = (
    0.4 * Math.sin(2 * Math.PI * f1 * t) +
    0.3 * Math.sin(2 * Math.PI * f2 * t + Math.sin(2 * Math.PI * 0.5 * t)) +
    0.2 * Math.sin(2 * Math.PI * f3 * t) +
    0.1 * Math.sin(2 * Math.PI * 110 * t) * Math.sin(2 * Math.PI * 0.3 * t)
  );
  return sig * lfo * 0.6;
});
writeFileSync('public/drone.wav', createWavBuffer(drone));
console.log('✓ drone.wav');

// --- 2. Water Drip (distorted, repeating) ---
// Short percussive drip sounds
const drip = generateSamples(15, (t) => {
  // Drips every ~1.2 seconds with slight randomization via modulation
  const dripInterval = 1.2;
  const phase = t % dripInterval;
  if (phase > 0.15) return 0;
  
  // Drip: short sine burst with pitch drop + distortion
  const env = Math.exp(-phase * 40);
  const freq = 800 - phase * 3000;
  let sig = Math.sin(2 * Math.PI * freq * phase) * env;
  // Add some harmonics for "distortion"
  sig += 0.3 * Math.sin(2 * Math.PI * freq * 2.7 * phase) * env;
  sig += 0.15 * Math.sin(2 * Math.PI * freq * 4.1 * phase) * env;
  // Soft clip
  sig = Math.tanh(sig * 2) * 0.5;
  return sig;
});
writeFileSync('public/drip.wav', createWavBuffer(drip));
console.log('✓ drip.wav');

// --- 3. Whoosh/Transition Sound ---
const whoosh = generateSamples(1.5, (t) => {
  // Rising noise burst
  const env = Math.sin(Math.PI * t / 1.5); // Bell curve envelope
  const brightness = 0.5 + t / 1.5; // Gets brighter over time
  // Filtered noise approximation using many sine waves
  let sig = 0;
  for (let h = 1; h <= 30; h++) {
    const freq = 200 * h * brightness;
    if (freq > 15000) break;
    sig += (Math.sin(2 * Math.PI * freq * t + h * 7.3) / h) * 0.1;
  }
  // Add a clean rising tone
  const riseTone = Math.sin(2 * Math.PI * (400 + t * 2000) * t) * 0.3;
  return (sig + riseTone) * env * 0.7;
});
writeFileSync('public/whoosh.wav', createWavBuffer(whoosh));
console.log('✓ whoosh.wav');

// --- 4. Chime (crystalline transition) ---
const chime = generateSamples(2, (t) => {
  const env = Math.exp(-t * 3);
  const sig = (
    0.4 * Math.sin(2 * Math.PI * 1318.5 * t) + // E6
    0.3 * Math.sin(2 * Math.PI * 1568 * t) +   // G6
    0.2 * Math.sin(2 * Math.PI * 2093 * t) +   // C7
    0.1 * Math.sin(2 * Math.PI * 2637 * t)     // E7
  );
  return sig * env * 0.6;
});
writeFileSync('public/chime.wav', createWavBuffer(chime));
console.log('✓ chime.wav');

// --- 5. Uplifting Background Music (15 seconds) ---
// Simple bright chord progression
const bright = generateSamples(15, (t) => {
  // C major arpeggiated feel
  const chords = [
    [261.6, 329.6, 392.0, 523.3], // C major
    [293.7, 370.0, 440.0, 587.3], // D major  
    [329.6, 415.3, 493.9, 659.3], // E major
    [349.2, 440.0, 523.3, 698.5], // F major
  ];
  const chordIndex = Math.floor((t % 8) / 2);
  const chord = chords[chordIndex];
  
  let sig = 0;
  for (let i = 0; i < chord.length; i++) {
    // Gentle sine tones with slight detuning for warmth
    sig += Math.sin(2 * Math.PI * chord[i] * t) * 0.15;
    sig += Math.sin(2 * Math.PI * chord[i] * 1.002 * t) * 0.05; // Chorus effect
  }
  
  // Add a gentle rhythmic pulse
  const pulse = 0.7 + 0.3 * Math.sin(2 * Math.PI * 2 * t);
  
  // Add sparkle
  const sparkle = Math.sin(2 * Math.PI * 1047 * t) * Math.sin(2 * Math.PI * 0.5 * t) * 0.05;
  
  return (sig * pulse + sparkle) * 0.6;
});
writeFileSync('public/bright-music.wav', createWavBuffer(bright));
console.log('✓ bright-music.wav');

// --- 6. Gentle Water Sound (clean, pleasant) ---
const gentleWater = generateSamples(15, (t) => {
  // Multiple layered "trickle" sounds
  let sig = 0;
  for (let i = 0; i < 5; i++) {
    const phase = (t * (1.1 + i * 0.37) + i * 2.1) % 0.8;
    if (phase < 0.1) {
      const env = Math.exp(-phase * 50);
      const freq = 2000 + i * 500 + Math.sin(t * 3 + i) * 200;
      sig += Math.sin(2 * Math.PI * freq * phase) * env * 0.1;
    }
  }
  // Soft background wash
  const wash = (
    Math.sin(2 * Math.PI * 220 * t + Math.sin(2 * Math.PI * 0.7 * t) * 2) * 0.02 +
    Math.sin(2 * Math.PI * 440 * t + Math.sin(2 * Math.PI * 1.1 * t) * 3) * 0.01
  );
  return (sig + wash) * 0.8;
});
writeFileSync('public/gentle-water.wav', createWavBuffer(gentleWater));
console.log('✓ gentle-water.wav');

console.log('\nAll audio assets generated.');
