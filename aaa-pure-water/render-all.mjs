import { execSync } from "child_process";

const compositions = ["ReverseOsmosis", "WholeHouse", "WaterSoftener"];
const outputDir = "out";

for (const comp of compositions) {
  const outFile = `${outputDir}/${comp}.mp4`;
  console.log(`\n🎬 Rendering ${comp}...`);
  execSync(
    `npx remotion render ${comp} ${outFile} --codec h264`,
    { stdio: "inherit" }
  );
  console.log(`✅ ${outFile}`);
}

console.log("\n🎉 All videos rendered!");
