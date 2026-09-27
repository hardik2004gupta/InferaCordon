import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "InferaCordon",
    short_name: "InferaCordon",
    description: "Governed AI inference control plane - reasoning compute made schedulable, policy-bounded, and quality-guaranteed.",
    start_url: "/",
    display: "standalone",
    background_color: "#F8F8F6",
    theme_color: "#3730A3",
  };
}
