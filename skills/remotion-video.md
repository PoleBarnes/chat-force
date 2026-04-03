# Skill: Remotion Video Ad Production

## What This Covers
Creating programmatic video ads using [Remotion](https://remotion.dev) — React-based video generation rendered to MP4.

## Project Setup

```bash
mkdir -p my-project/src my-project/public
cd my-project
```

### package.json essentials
```json
{
  "dependencies": {
    "@remotion/cli": "4.0.301",
    "remotion": "4.0.301",
    "react": "^19",
    "react-dom": "^19"
  }
}
```

**Pin all `@remotion/*` packages to the same version** — version mismatches cause cryptic errors.

### Entry point (`src/index.ts`)
Must call `registerRoot()`:
```ts
import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";
registerRoot(RemotionRoot);
```

### Config (`remotion.config.ts`)
```ts
import { Config } from "@remotion/cli/config";
Config.setEntryPoint("./src/index.ts");
```

## Core Concepts

### Composition Registration (`src/Root.tsx`)
```tsx
<Composition
  id="MyVideo"
  component={MyComponent}
  durationInFrames={450}  // 15 sec @ 30fps
  fps={30}
  width={1080}
  height={1080}
  defaultProps={{ variant: "a" }}
/>
```

Register multiple compositions to render variants from the same codebase.

### Timing with Sequences
```tsx
<Sequence from={0} durationInFrames={150}>   {/* Act 1: 0-5s */}
<Sequence from={150} durationInFrames={45}>   {/* Act 2: 5-6.5s */}
<Sequence from={195} durationInFrames={150}>  {/* Act 3: 6.5-11.5s */}
<Sequence from={345} durationInFrames={105}>  {/* Act 4: 11.5-15s */}
```

Children of `<Sequence>` get time-shifted `useCurrentFrame()` values (starts at 0 within each sequence).

### Animation with `interpolate()`
```tsx
const frame = useCurrentFrame();
const opacity = interpolate(frame, [0, 20], [0, 1], {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
});
```

Multi-point interpolation for fade-in/fade-out:
```tsx
interpolate(frame, [0, 20, durationInFrames - 20, durationInFrames], [0, 1, 1, 0]);
```

## Audio

### Component (v4.0.x)
In Remotion 4.0.301: use `Audio` from `remotion`.  
In later versions: renamed to `Html5Audio` (import from `remotion`), or use `@remotion/media`'s `Audio`.

### Static volume
```tsx
<Audio src={staticFile("music.wav")} volume={0.5} />
```

### Per-frame volume automation (fade in/out)
```tsx
<Audio
  src={staticFile("drone.wav")}
  volume={(f) => {
    const fadeIn = interpolate(f, [0, 15], [0, 0.7], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    const fadeOut = interpolate(f, [130, 150], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    return fadeIn * fadeOut;
  }}
/>
```

### Layering multiple audio tracks
Just render multiple `<Audio>` components — they mix automatically:
```tsx
<>
  <Sequence durationInFrames={150}>
    <Audio src={staticFile("drone.wav")} volume={0.7} />
  </Sequence>
  <Sequence durationInFrames={150}>
    <Audio src={staticFile("drip.wav")} volume={0.5} />
  </Sequence>
  <Sequence from={150} durationInFrames={45}>
    <Audio src={staticFile("whoosh.wav")} volume={0.8} />
  </Sequence>
</>
```

### Generating audio programmatically
When stock audio isn't available, synthesize WAV files with Node.js:
- Create PCM samples as Float64Array
- Write RIFF/WAV header + 16-bit PCM data
- Place files in `public/` directory, reference with `staticFile()`

Key synthesis techniques:
- **Drone:** Layer detuned sine waves with LFO modulation
- **Drips:** Short sine bursts with exponential decay + pitch drop
- **Whoosh:** Rising filtered noise (sum of harmonics) + rising tone
- **Chime:** Stacked harmonic sine waves with exponential decay
- **Music:** Chord progressions with chorus detuning + rhythmic pulse

## Headless Rendering

### Browser dependencies (Docker/minimal Linux)
Remotion's headless Chrome needs system libraries. If you can't install via apt:

```bash
# Download .deb packages and extract .so files to a local dir
dpkg-deb -x package.deb /tmp/extract/
cp /tmp/extract/usr/lib/*/lib*.so* ~/.local/lib/chromium/

# Required packages (Debian bookworm arm64):
# libnss3, libnspr4, libdbus-1-3, libatk1.0-0, libatspi2.0-0,
# libxcomposite1, libxdamage1, libxfixes3, libxrandr2, libgbm1,
# libxkbcommon0, libasound2, libxi6, libdrm2, libwayland-server0
```

### Render command
```bash
LD_LIBRARY_PATH="$HOME/.local/lib/chromium" \
  npx remotion render CompositionId out/video.mp4 --codec h264
```

### Batch render
```js
const compositions = ["Ad1", "Ad2", "Ad3"];
for (const comp of compositions) {
  execSync(`npx remotion render ${comp} out/${comp}.mp4 --codec h264`);
}
```

## Ad Structure Pattern (4-Act)

| Act | Frames (30fps) | Duration | Purpose |
|-----|----------------|----------|---------|
| 1 - Problem | 0–149 | 5s | Dark mood, pain point |
| 2 - Transition | 150–194 | 1.5s | Dark→bright shift |
| 3 - Solution | 195–344 | 5s | Bright, product reveal |
| 4 - CTA | 345–449 | 3.5s | URL + tagline |

Audio should cross-fade between acts — start fading out Act 1 audio slightly before the visual transition, and fade in Act 3 audio slightly after.

## Specs for Facebook Video Ads
- **Dimensions:** 1080×1080 (square)
- **FPS:** 30
- **Duration:** 15 seconds
- **Codec:** H.264 (MP4)
- **File size:** Keep under 4GB (Facebook limit), aim for <10MB
