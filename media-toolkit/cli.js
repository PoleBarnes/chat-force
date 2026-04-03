#!/usr/bin/env node
const { Command } = require('commander');
const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const program = new Command();

// Resolve ffmpeg/ffprobe — prefer user-local static build, then system PATH
function findBin(name) {
  const localBin = path.join(process.env.HOME || '', 'bin', name);
  if (fs.existsSync(localBin)) return localBin;
  return name; // fall back to PATH
}

const FFMPEG = findBin('ffmpeg');
const FFPROBE = findBin('ffprobe');

program
  .name('media-toolkit')
  .description('CLI media utilities powered by ffmpeg and ImageMagick')
  .version('1.0.0');

// ── video-to-gif ──────────────────────────────────────────────
program
  .command('video-to-gif')
  .description('Convert a video file to an animated GIF')
  .argument('<input>', 'Input video file')
  .argument('<output>', 'Output GIF file')
  .option('-w, --width <px>', 'Output width in pixels', '480')
  .option('-r, --fps <n>', 'Frames per second', '10')
  .action((input, output, opts) => {
    if (!fs.existsSync(input)) {
      console.error(`Error: input file not found: ${input}`);
      process.exit(1);
    }
    const filterGraph = `fps=${opts.fps},scale=${opts.width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse`;
    const args = [
      '-y', '-i', input,
      '-vf', filterGraph,
      '-loop', '0',
      output,
    ];
    console.log(`Converting ${input} → ${output} (${opts.width}px, ${opts.fps}fps)`);
    execFileSync(FFMPEG, args, { stdio: 'inherit' });
    console.log('Done.');
  });

// ── thumbnails ────────────────────────────────────────────────
program
  .command('thumbnails')
  .description('Create a thumbnail grid from a video')
  .argument('<input>', 'Input video file')
  .argument('<output>', 'Output image file (e.g. grid.png)')
  .option('-c, --cols <n>', 'Number of columns', '4')
  .option('-r, --rows <n>', 'Number of rows', '4')
  .option('-w, --width <px>', 'Width of each thumbnail', '320')
  .action((input, output, opts) => {
    if (!fs.existsSync(input)) {
      console.error(`Error: input file not found: ${input}`);
      process.exit(1);
    }
    const cols = parseInt(opts.cols, 10);
    const rows = parseInt(opts.rows, 10);
    const totalFrames = cols * rows;

    // Get duration
    const durationStr = execFileSync(FFPROBE, [
      '-v', 'error',
      '-show_entries', 'format=duration',
      '-of', 'csv=p=0',
      input,
    ], { encoding: 'utf8' }).trim();
    const duration = parseFloat(durationStr);
    if (!duration || duration <= 0) {
      console.error('Could not determine video duration.');
      process.exit(1);
    }

    const interval = duration / (totalFrames + 1);
    const tmpDir = fs.mkdtempSync(path.join(require('os').tmpdir(), 'thumbs-'));
    const thumbFiles = [];

    console.log(`Extracting ${totalFrames} thumbnails from ${input} (${duration.toFixed(1)}s)...`);
    for (let i = 0; i < totalFrames; i++) {
      const ts = ((i + 1) * interval).toFixed(3);
      const thumbPath = path.join(tmpDir, `thumb_${String(i).padStart(3, '0')}.png`);
      execFileSync(FFMPEG, [
        '-y', '-ss', ts, '-i', input,
        '-vframes', '1',
        '-vf', `scale=${opts.width}:-1`,
        thumbPath,
      ], { stdio: 'pipe' });
      thumbFiles.push(thumbPath);
    }

    // Use ImageMagick montage
    const montageArgs = [
      ...thumbFiles,
      '-tile', `${cols}x${rows}`,
      '-geometry', '+2+2',
      output,
    ];
    console.log('Building grid...');
    execFileSync('montage', montageArgs, { stdio: 'inherit' });

    // Cleanup
    thumbFiles.forEach(f => { try { fs.unlinkSync(f); } catch {} });
    try { fs.rmdirSync(tmpDir); } catch {}

    console.log(`Done → ${output}`);
  });

// ── watermark ─────────────────────────────────────────────────
program
  .command('watermark')
  .description('Add a watermark overlay to an image')
  .argument('<image>', 'Base image file')
  .argument('<watermark>', 'Watermark image file')
  .argument('<output>', 'Output image file')
  .option('-g, --gravity <pos>', 'Placement gravity', 'SouthEast')
  .option('-o, --opacity <pct>', 'Watermark opacity (0-100)', '30')
  .action((image, watermark, output, opts) => {
    if (!fs.existsSync(image)) {
      console.error(`Error: image file not found: ${image}`);
      process.exit(1);
    }
    if (!fs.existsSync(watermark)) {
      console.error(`Error: watermark file not found: ${watermark}`);
      process.exit(1);
    }
    const dissolve = parseInt(opts.opacity, 10);
    const args = [
      '-dissolve', `${dissolve}`,
      '-gravity', opts.gravity,
      watermark,
      image,
      output,
    ];
    console.log(`Watermarking ${image} → ${output} (gravity=${opts.gravity}, opacity=${opts.opacity}%)`);
    execFileSync('composite', args, { stdio: 'inherit' });
    console.log('Done.');
  });

// ── waveform ──────────────────────────────────────────────────
program
  .command('waveform')
  .description('Generate a waveform visualization from an audio file')
  .argument('<input>', 'Input audio file')
  .argument('<output>', 'Output PNG file')
  .option('-s, --size <WxH>', 'Output dimensions', '1920x200')
  .option('--color <hex>', 'Waveform colour', '0x00cc88')
  .action((input, output, opts) => {
    if (!fs.existsSync(input)) {
      console.error(`Error: input file not found: ${input}`);
      process.exit(1);
    }
    const args = [
      '-y', '-i', input,
      '-filter_complex', `showwavespic=s=${opts.size}:colors=${opts.color}`,
      '-frames:v', '1',
      output,
    ];
    console.log(`Generating waveform for ${input} → ${output}`);
    execFileSync(FFMPEG, args, { stdio: 'inherit' });
    console.log('Done.');
  });

program.parse();
