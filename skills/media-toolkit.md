# Media Toolkit Skill

CLI tool for common media operations powered by ffmpeg and ImageMagick.

## Location

`/workspace/config/media-toolkit/`

## Prerequisites

- **ffmpeg** — static binary installed at `~/bin/ffmpeg` (or system PATH)
- **ImageMagick** — system install (`convert`, `composite`, `montage` commands)
- **Node.js** — v18+

## Commands

### Convert Video to GIF

```bash
node media-toolkit/cli.js video-to-gif <input.mp4> <output.gif> [--width 480] [--fps 10]
```

Uses ffmpeg with palettegen for high-quality GIF output.

### Create Thumbnail Grid

```bash
node media-toolkit/cli.js thumbnails <input.mp4> <grid.png> [--cols 4] [--rows 4] [--width 320]
```

Extracts evenly-spaced frames and assembles them with ImageMagick `montage`.

### Add Watermark

```bash
node media-toolkit/cli.js watermark <image.png> <watermark.png> <output.png> [--gravity SouthEast] [--opacity 30]
```

Uses ImageMagick `composite` with dissolve for transparent overlay.

### Generate Waveform

```bash
node media-toolkit/cli.js waveform <input.wav> <output.png> [--size 1920x200] [--color 0x00cc88]
```

Uses ffmpeg `showwavespic` filter.

## Security

All shell execution uses `execFileSync` with argument arrays — no string interpolation or shell expansion. No command injection vectors.

## Testing

```bash
cd media-toolkit && npm test
```

Tests create synthetic media files (video, audio, images) programmatically and validate each command produces valid output.

## Architecture Notes

- CLI parsing via `commander.js`
- Each command validates input file existence before shelling out
- ffmpeg resolved via `~/bin/` first, then system PATH (supports static binary installs)
- Temp files for thumbnail grid cleaned up after montage
