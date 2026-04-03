import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Resolve ffmpeg
function findBin(name) {
  const localBin = path.join(process.env.HOME || '', 'bin', name);
  if (fs.existsSync(localBin)) return localBin;
  return name;
}
const FFMPEG = findBin('ffmpeg');

const CLI = path.join(__dirname, 'cli.js');
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'media-toolkit-test-'));

// Helper: create a short test video (1s, 320x240, solid colour)
function createTestVideo(outPath) {
  execFileSync(FFMPEG, [
    '-y', '-f', 'lavfi', '-i',
    'color=c=blue:s=320x240:d=2:r=10',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
    '-t', '2',
    outPath,
  ], { stdio: 'pipe' });
}

// Helper: create a test audio file (1s sine wave)
function createTestAudio(outPath) {
  execFileSync(FFMPEG, [
    '-y', '-f', 'lavfi', '-i',
    'sine=frequency=440:duration=2',
    outPath,
  ], { stdio: 'pipe' });
}

// Helper: create a test image (solid red 200x200)
function createTestImage(outPath, color = 'red', size = '200x200') {
  execFileSync('convert', [
    '-size', size, `xc:${color}`, outPath,
  ], { stdio: 'pipe' });
}

// ── Setup / Teardown ──────────────────────────────────────────
const testVideo = path.join(TMP, 'test.mp4');
const testAudio = path.join(TMP, 'test.wav');
const testImage = path.join(TMP, 'test.png');
const testWatermark = path.join(TMP, 'watermark.png');

beforeAll(() => {
  createTestVideo(testVideo);
  createTestAudio(testAudio);
  createTestImage(testImage, 'red', '200x200');
  createTestImage(testWatermark, 'white', '50x50');
});

afterAll(() => {
  fs.rmSync(TMP, { recursive: true, force: true });
});

// ── Tests ─────────────────────────────────────────────────────

describe('CLI --help', () => {
  it('shows help text', () => {
    const out = execFileSync('node', [CLI, '--help'], { encoding: 'utf8' });
    expect(out).toContain('media-toolkit');
    expect(out).toContain('video-to-gif');
    expect(out).toContain('thumbnails');
    expect(out).toContain('watermark');
    expect(out).toContain('waveform');
  });
});

describe('video-to-gif', () => {
  it('converts a video to GIF', () => {
    const output = path.join(TMP, 'out.gif');
    execFileSync('node', [CLI, 'video-to-gif', testVideo, output], { stdio: 'pipe' });
    expect(fs.existsSync(output)).toBe(true);
    const stat = fs.statSync(output);
    expect(stat.size).toBeGreaterThan(100);
  });

  it('fails on missing input', () => {
    const output = path.join(TMP, 'nope.gif');
    expect(() => {
      execFileSync('node', [CLI, 'video-to-gif', '/nonexistent.mp4', output], {
        stdio: 'pipe',
      });
    }).toThrow();
  });
});

describe('thumbnails', () => {
  it('creates a thumbnail grid', () => {
    const output = path.join(TMP, 'grid.png');
    execFileSync('node', [CLI, 'thumbnails', testVideo, output, '--cols', '2', '--rows', '2'], {
      stdio: 'pipe',
    });
    expect(fs.existsSync(output)).toBe(true);
    const stat = fs.statSync(output);
    expect(stat.size).toBeGreaterThan(100);
  });
});

describe('watermark', () => {
  it('applies a watermark to an image', () => {
    const output = path.join(TMP, 'watermarked.png');
    execFileSync('node', [CLI, 'watermark', testImage, testWatermark, output], {
      stdio: 'pipe',
    });
    expect(fs.existsSync(output)).toBe(true);
    const stat = fs.statSync(output);
    expect(stat.size).toBeGreaterThan(100);
  });

  it('fails on missing image', () => {
    const output = path.join(TMP, 'nope.png');
    expect(() => {
      execFileSync('node', [CLI, 'watermark', '/nonexistent.png', testWatermark, output], {
        stdio: 'pipe',
      });
    }).toThrow();
  });
});

describe('waveform', () => {
  it('generates a waveform from audio', () => {
    const output = path.join(TMP, 'waveform.png');
    execFileSync('node', [CLI, 'waveform', testAudio, output], { stdio: 'pipe' });
    expect(fs.existsSync(output)).toBe(true);
    const stat = fs.statSync(output);
    expect(stat.size).toBeGreaterThan(100);
  });

  it('fails on missing input', () => {
    const output = path.join(TMP, 'nope.png');
    expect(() => {
      execFileSync('node', [CLI, 'waveform', '/nonexistent.wav', output], {
        stdio: 'pipe',
      });
    }).toThrow();
  });
});
