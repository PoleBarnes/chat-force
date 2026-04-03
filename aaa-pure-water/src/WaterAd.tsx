import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
} from "remotion";

type Product = "ro" | "wh" | "ws";

const PRODUCT_DATA: Record<Product, { solutionText: string; subtitle: string }> = {
  ro: {
    solutionText: "Reverse Osmosis",
    subtitle: "99.9% pure drinking water",
  },
  wh: {
    solutionText: "Whole House Filtration",
    subtitle: "Clean water from every tap",
  },
  ws: {
    solutionText: "Water Softeners",
    subtitle: "No more scale & buildup",
  },
};

// ============================================================
// ACT 1 — THE PROBLEM (frames 0–149, 5 seconds)
// ============================================================
const Act1Problem: React.FC = () => {
  const frame = useCurrentFrame();

  // Murky water background animation
  const bgDarkness = interpolate(frame, [0, 150], [0.85, 0.95], {
    extrapolateRight: "clamp",
  });
  const pulseGlow = Math.sin(frame * 0.05) * 0.03;

  // Text animation
  const textOpacity = interpolate(frame, [15, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const textY = interpolate(frame, [15, 40], [30, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Subtle shake effect
  const shakeX = Math.sin(frame * 0.7) * 1.5;
  const shakeY = Math.cos(frame * 0.9) * 1;

  // Water droplet particles
  const droplets = Array.from({ length: 8 }, (_, i) => {
    const speed = 0.5 + (i * 0.3);
    const x = 150 + (i * 120) % 900;
    const y = ((frame * speed + i * 80) % 1200) - 100;
    const size = 3 + (i % 3) * 2;
    const opacity = interpolate(y, [0, 200, 1000, 1100], [0, 0.4, 0.4, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    return { x, y, size, opacity };
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0a0806",
        transform: `translate(${shakeX}px, ${shakeY}px)`,
      }}
    >
      {/* Murky water gradient overlay */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(ellipse at 50% 60%, 
            rgba(89, 62, 26, ${0.3 + pulseGlow}) 0%, 
            rgba(43, 29, 14, ${bgDarkness}) 50%, 
            rgba(10, 8, 6, 1) 100%)`,
        }}
      />

      {/* Murky water streaks */}
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            width: "200%",
            height: 200,
            top: 300 + i * 180,
            left: -200 + Math.sin(frame * 0.02 + i) * 100,
            background: `linear-gradient(90deg, transparent, rgba(120, 80, 30, 0.08), transparent)`,
            transform: `rotate(${-5 + i * 3}deg)`,
          }}
        />
      ))}

      {/* Floating droplets */}
      {droplets.map((d, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: d.x,
            top: d.y,
            width: d.size,
            height: d.size * 1.4,
            borderRadius: "50% 50% 50% 50% / 30% 30% 70% 70%",
            backgroundColor: `rgba(140, 100, 50, ${d.opacity})`,
          }}
        />
      ))}

      {/* Stain/mineral buildup circles */}
      {[0, 1, 2].map((i) => {
        const cx = [280, 700, 500][i];
        const cy = [350, 500, 750][i];
        const r = [80, 60, 100][i];
        const o = interpolate(frame, [30 + i * 20, 60 + i * 20], [0, 0.15], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <div
            key={`stain-${i}`}
            style={{
              position: "absolute",
              left: cx - r,
              top: cy - r,
              width: r * 2,
              height: r * 2,
              borderRadius: "50%",
              border: `2px solid rgba(180, 130, 60, ${o})`,
              background: `radial-gradient(circle, rgba(100, 70, 20, ${o * 0.5}), transparent)`,
            }}
          />
        );
      })}

      {/* Main text */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          opacity: textOpacity,
          transform: `translateY(${textY}px)`,
        }}
      >
        <div
          style={{
            fontSize: 72,
            fontWeight: 800,
            color: "#d4a854",
            textAlign: "center",
            fontFamily: "Arial, Helvetica, sans-serif",
            textShadow: "0 0 40px rgba(180, 130, 50, 0.5), 0 4px 12px rgba(0,0,0,0.8)",
            letterSpacing: -1,
            lineHeight: 1.1,
            padding: "0 60px",
          }}
        >
          Your water is
          <br />
          hiding something.
        </div>
      </div>

      {/* Vignette */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.6) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

// ============================================================
// ACT 2 — THE TRANSITION (frames 150–194, ~1.5 seconds)
// ============================================================
const Act2Transition: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Wipe from dark to bright
  const wipeProgress = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateRight: "clamp",
  });

  const circleRadius = interpolate(wipeProgress, [0, 1], [0, 1600], {
    extrapolateRight: "clamp",
  });

  const flashOpacity = interpolate(frame, [15, 25, 45], [0, 0.8, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0806" }}>
      {/* Expanding bright circle */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          width: circleRadius * 2,
          height: circleRadius * 2,
          marginLeft: -circleRadius,
          marginTop: -circleRadius,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, #ffffff 0%, #e8f4fd 40%, #b8dff5 70%, #87ceeb 100%)",
        }}
      />

      {/* Flash overlay */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundColor: `rgba(255, 255, 255, ${flashOpacity})`,
        }}
      />
    </AbsoluteFill>
  );
};

// ============================================================
// ACT 3 — THE SOLUTION (frames 195–344, 5 seconds)
// ============================================================
const Act3Solution: React.FC<{ product: Product }> = ({ product }) => {
  const frame = useCurrentFrame();
  const data = PRODUCT_DATA[product];

  const textOpacity = interpolate(frame, [10, 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const textY = interpolate(frame, [10, 30], [40, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const subtitleOpacity = interpolate(frame, [30, 50], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Water ripple rings
  const ripples = Array.from({ length: 3 }, (_, i) => {
    const delay = i * 30;
    const rippleFrame = Math.max(0, frame - delay);
    const radius = interpolate(rippleFrame, [0, 90], [0, 400], {
      extrapolateRight: "clamp",
    });
    const opacity = interpolate(rippleFrame, [0, 20, 90], [0, 0.3, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    return { radius, opacity };
  });

  // Sparkle particles
  const sparkles = Array.from({ length: 12 }, (_, i) => {
    const angle = (i / 12) * Math.PI * 2 + frame * 0.01;
    const dist = 200 + Math.sin(frame * 0.03 + i * 2) * 100;
    const x = 540 + Math.cos(angle) * dist;
    const y = 540 + Math.sin(angle) * dist;
    const size = 4 + Math.sin(frame * 0.1 + i) * 2;
    const opacity = 0.3 + Math.sin(frame * 0.08 + i * 1.5) * 0.3;
    return { x, y, size, opacity };
  });

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(180deg, #e8f4fd 0%, #ffffff 30%, #f0f9ff 70%, #dceefb 100%)",
      }}
    >
      {/* Water ripples */}
      {ripples.map((r, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: 540 - r.radius,
            top: 600 - r.radius,
            width: r.radius * 2,
            height: r.radius * 2,
            borderRadius: "50%",
            border: `2px solid rgba(59, 130, 246, ${r.opacity})`,
          }}
        />
      ))}

      {/* Sparkles */}
      {sparkles.map((s, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: s.x - s.size / 2,
            top: s.y - s.size / 2,
            width: s.size,
            height: s.size,
            borderRadius: "50%",
            backgroundColor: `rgba(59, 130, 246, ${s.opacity})`,
            boxShadow: `0 0 ${s.size * 2}px rgba(59, 130, 246, ${s.opacity * 0.5})`,
          }}
        />
      ))}

      {/* Clean water glass illustration */}
      <div
        style={{
          position: "absolute",
          left: 540 - 80,
          top: 280,
          width: 160,
          height: 220,
          borderRadius: "0 0 30px 30px",
          border: "3px solid rgba(59, 130, 246, 0.3)",
          background: "linear-gradient(180deg, rgba(59, 130, 246, 0.05) 0%, rgba(59, 130, 246, 0.15) 100%)",
          overflow: "hidden",
        }}
      >
        {/* Water level in glass */}
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: "70%",
            background: "linear-gradient(180deg, rgba(59, 165, 246, 0.2) 0%, rgba(59, 130, 246, 0.35) 100%)",
            borderRadius: "0 0 27px 27px",
          }}
        />
      </div>

      {/* Product text */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          paddingTop: 300,
        }}
      >
        <div
          style={{
            fontSize: 64,
            fontWeight: 800,
            color: "#1e3a5f",
            textAlign: "center",
            fontFamily: "Arial, Helvetica, sans-serif",
            opacity: textOpacity,
            transform: `translateY(${textY}px)`,
            letterSpacing: -1,
          }}
        >
          {data.solutionText}
        </div>
        <div
          style={{
            fontSize: 36,
            fontWeight: 500,
            color: "#3b82f6",
            textAlign: "center",
            fontFamily: "Arial, Helvetica, sans-serif",
            marginTop: 16,
            opacity: subtitleOpacity,
          }}
        >
          {data.subtitle}
        </div>
      </div>

      {/* AAA Logo area */}
      <div
        style={{
          position: "absolute",
          top: 60,
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            fontSize: 32,
            fontWeight: 900,
            color: "#1e3a5f",
            fontFamily: "Arial, Helvetica, sans-serif",
            letterSpacing: 3,
            opacity: interpolate(frame, [0, 20], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        >
          AAA PURE WATER
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ============================================================
// ACT 4 — CTA (frames 345–449, ~3.5 seconds)
// ============================================================
const Act4CTA: React.FC = () => {
  const frame = useCurrentFrame();

  const mainOpacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const urlScale = interpolate(frame, [5, 25], [0.9, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const taglineOpacity = interpolate(frame, [20, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(180deg, #f0f9ff 0%, #ffffff 50%, #e8f4fd 100%)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {/* URL */}
      <div
        style={{
          fontSize: 52,
          fontWeight: 900,
          color: "#1e3a5f",
          fontFamily: "Arial, Helvetica, sans-serif",
          opacity: mainOpacity,
          transform: `scale(${urlScale})`,
          letterSpacing: 0,
        }}
      >
        aaapurewaterdistillers.com
      </div>

      {/* Divider */}
      <div
        style={{
          width: 120,
          height: 3,
          backgroundColor: "#3b82f6",
          marginTop: 30,
          marginBottom: 30,
          opacity: mainOpacity,
          borderRadius: 2,
        }}
      />

      {/* Tagline */}
      <div
        style={{
          fontSize: 40,
          fontWeight: 600,
          color: "#3b82f6",
          fontFamily: "Arial, Helvetica, sans-serif",
          opacity: taglineOpacity,
        }}
      >
        Clean water starts here.
      </div>
    </AbsoluteFill>
  );
};

// ============================================================
// AUDIO LAYER
// ============================================================
const AudioLayer: React.FC = () => {
  const { fps, durationInFrames } = useVideoConfig();

  // Act boundaries in frames
  const ACT1_END = 150; // 5 sec
  const ACT2_START = 150;
  const ACT2_END = 195; // 1.5 sec
  const ACT3_START = 195;
  const ACT3_END = 345; // 5 sec  
  const ACT4_START = 345;

  return (
    <>
      {/* === ACT 1: Ominous Drone === */}
      <Sequence durationInFrames={ACT2_END}>
        <Audio
          src={staticFile("drone.wav")}
          volume={(f) => {
            // Fade in over first 15 frames, sustain, fade out during transition
            const fadeIn = interpolate(f, [0, 15], [0, 0.7], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const fadeOut = interpolate(f, [ACT1_END, ACT2_END], [1, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return fadeIn * fadeOut;
          }}
        />
      </Sequence>

      {/* === ACT 1: Water Drip SFX === */}
      <Sequence durationInFrames={ACT1_END + 15}>
        <Audio
          src={staticFile("drip.wav")}
          volume={(f) => {
            const fadeIn = interpolate(f, [0, 30], [0, 0.5], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const fadeOut = interpolate(f, [ACT1_END - 10, ACT1_END + 15], [1, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return fadeIn * fadeOut;
          }}
        />
      </Sequence>

      {/* === ACT 2: Whoosh Transition === */}
      <Sequence from={ACT2_START - 5} durationInFrames={55}>
        <Audio
          src={staticFile("whoosh.wav")}
          volume={(f) => {
            return interpolate(f, [0, 15, 45, 55], [0, 0.8, 0.3, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
          }}
        />
      </Sequence>

      {/* === ACT 2: Chime === */}
      <Sequence from={ACT2_START + 10} durationInFrames={60}>
        <Audio
          src={staticFile("chime.wav")}
          volume={(f) => {
            return interpolate(f, [0, 5, 50, 60], [0, 0.6, 0.2, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
          }}
        />
      </Sequence>

      {/* === ACT 3+4: Bright Uplifting Music === */}
      <Sequence from={ACT3_START - 10} durationInFrames={durationInFrames - ACT3_START + 10}>
        <Audio
          src={staticFile("bright-music.wav")}
          volume={(f) => {
            const fadeIn = interpolate(f, [0, 30], [0, 0.6], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            // Resolve/fade at the very end
            const totalFrames = durationInFrames - ACT3_START + 10;
            const fadeOut = interpolate(f, [totalFrames - 20, totalFrames], [1, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return fadeIn * fadeOut;
          }}
        />
      </Sequence>

      {/* === ACT 3: Gentle Water SFX === */}
      <Sequence from={ACT3_START} durationInFrames={ACT3_END - ACT3_START}>
        <Audio
          src={staticFile("gentle-water.wav")}
          volume={(f) => {
            const fadeIn = interpolate(f, [0, 20], [0, 0.35], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const dur = ACT3_END - ACT3_START;
            const fadeOut = interpolate(f, [dur - 15, dur], [1, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return fadeIn * fadeOut;
          }}
        />
      </Sequence>
    </>
  );
};

// ============================================================
// MAIN COMPOSITION
// ============================================================
export const WaterAd: React.FC<{ product: Product }> = ({ product }) => {
  return (
    <AbsoluteFill>
      {/* Act 1: The Problem — frames 0-149 (5 seconds) */}
      <Sequence durationInFrames={150}>
        <Act1Problem />
      </Sequence>

      {/* Act 2: The Transition — frames 150-194 (1.5 seconds) */}
      <Sequence from={150} durationInFrames={45}>
        <Act2Transition />
      </Sequence>

      {/* Act 3: The Solution — frames 195-344 (5 seconds) */}
      <Sequence from={195} durationInFrames={150}>
        <Act3Solution product={product} />
      </Sequence>

      {/* Act 4: CTA — frames 345-449 (3.5 seconds) */}
      <Sequence from={345} durationInFrames={105}>
        <Act4CTA />
      </Sequence>

      {/* Audio overlay (spans all acts) */}
      <AudioLayer />
    </AbsoluteFill>
  );
};
