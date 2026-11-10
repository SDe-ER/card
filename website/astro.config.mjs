// CARD documentation site — Astro Starlight, published to GitHub Pages (https://sde-er.github.io/card/).
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  site: "https://sde-er.github.io",
  base: "/card",
  integrations: [
    starlight({
      title: "CARD",
      description: "Equipment management for Frappe / ERPNext — documentation",
      logo: { src: "./src/assets/card-logo.svg", alt: "CARD" },
      favicon: "/favicon.svg",
      defaultLocale: "root",
      locales: {
        root: { label: "English", lang: "en" },
        ar: { label: "العربية", lang: "ar", dir: "rtl" },
      },
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/SDe-ER/card",
        },
      ],
      customCss: ["./src/styles/custom.css"],
      lastUpdated: false,
      sidebar: [
        {
          label: "Getting Started",
          translations: { ar: "البداية" },
          items: [{ autogenerate: { directory: "getting-started" } }],
        },
        {
          label: "Features",
          translations: { ar: "المزايا" },
          items: [{ autogenerate: { directory: "features" } }],
        },
        {
          label: "Reports",
          translations: { ar: "التقارير" },
          items: [{ autogenerate: { directory: "reports" } }],
        },
        {
          label: "API Reference",
          translations: { ar: "مرجع الـ API" },
          items: [{ autogenerate: { directory: "api-reference" } }],
        },
      ],
    }),
  ],
});
