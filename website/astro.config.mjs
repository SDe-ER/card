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
      editLink: {
        baseUrl: "https://github.com/SDe-ER/card/edit/main/website/",
      },
      sidebar: [
        {
          label: "Getting Started",
          translations: { ar: "البداية" },
          items: [{ autogenerate: { directory: "getting-started" } }],
        },
        {
          label: "Releases",
          translations: { ar: "الإصدارات" },
          items: [{ autogenerate: { directory: "releases" } }],
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
        {
          // Generated from the code by scripts/generate_reference.py on every build.
          label: "Reference",
          translations: { ar: "المرجع" },
          collapsed: true,
          items: [
            { slug: "reference" },
            { slug: "reference/reports" },
            { slug: "reference/api-endpoints" },
            {
              label: "DocTypes",
              translations: { ar: "أنواع المستندات" },
              collapsed: true,
              items: [{ autogenerate: { directory: "reference/doctypes" } }],
            },
          ],
        },
      ],
    }),
  ],
});
