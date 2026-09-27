import type { MetadataRoute } from "next";

const BASE = "https://inferacordon.vercel.app";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: BASE, lastModified: new Date() },
    { url: `${BASE}/app`, lastModified: new Date() },
    { url: `${BASE}/app/playground`, lastModified: new Date() },
    { url: `${BASE}/app/observability`, lastModified: new Date() },
    { url: `${BASE}/app/policies`, lastModified: new Date() },
    { url: `${BASE}/app/audit`, lastModified: new Date() },
    { url: `${BASE}/app/health`, lastModified: new Date() },
  ];
}
