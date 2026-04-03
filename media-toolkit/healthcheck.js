#!/usr/bin/env node
/**
 * Media Toolkit Health Check
 * Verifies ffmpeg, ffprobe, and ImageMagick are available and functional.
 */
const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

function findBin(name) {
  const localBin = path.join(process.env.HOME || '', 'bin', name);
  if (fs.existsSync(localBin)) return localBin;
  return name;
}

const checks = [
  { name: 'ffmpeg', cmd: findBin('ffmpeg'), args: ['-version'] },
  { name: 'ffprobe', cmd: findBin('ffprobe'), args: ['-version'] },
  { name: 'convert (ImageMagick)', cmd: 'convert', args: ['--version'] },
  { name: 'composite (ImageMagick)', cmd: 'composite', args: ['--version'] },
  { name: 'montage (ImageMagick)', cmd: 'montage', args: ['--version'] },
];

let allOk = true;

for (const check of checks) {
  try {
    const out = execFileSync(check.cmd, check.args, { encoding: 'utf8', stdio: 'pipe' });
    const version = out.split('\n')[0].trim();
    console.log(`✅ ${check.name}: ${version}`);
  } catch (err) {
    console.error(`❌ ${check.name}: FAILED — ${err.message}`);
    allOk = false;
  }
}

if (allOk) {
  console.log('\n🟢 All checks passed.');
  process.exit(0);
} else {
  console.error('\n🔴 Some checks failed.');
  process.exit(1);
}
