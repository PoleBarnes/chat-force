import { Composition } from "remotion";
import { WaterAd } from "./WaterAd";

const FPS = 30;
const DURATION = 15 * FPS; // 15 seconds = 450 frames
const SIZE = 1080;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ReverseOsmosis"
        component={WaterAd}
        durationInFrames={DURATION}
        fps={FPS}
        width={SIZE}
        height={SIZE}
        defaultProps={{
          product: "ro" as const,
        }}
      />
      <Composition
        id="WholeHouse"
        component={WaterAd}
        durationInFrames={DURATION}
        fps={FPS}
        width={SIZE}
        height={SIZE}
        defaultProps={{
          product: "wh" as const,
        }}
      />
      <Composition
        id="WaterSoftener"
        component={WaterAd}
        durationInFrames={DURATION}
        fps={FPS}
        width={SIZE}
        height={SIZE}
        defaultProps={{
          product: "ws" as const,
        }}
      />
    </>
  );
};
