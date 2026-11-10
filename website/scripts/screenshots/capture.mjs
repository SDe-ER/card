// Capture the documentation screenshots from a CARD demo site seeded with seed_demo.py.
//
//   SITE=http://demo.localhost:8000 USER=Administrator PASS=admin node scripts/screenshots/capture.mjs [name ...]
//
// Writes website/src/assets/screenshots/{en,ar}/<name>.webp (1440x900 viewport at 2x, WebP quality 82).
// Use a disposable demo site with fictitious data only; never point this at a production site.
import { createRequire } from "node:module";
import sharp from "sharp";
import { readFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// Playwright is not a site dependency; use the copy installed on the machine (NODE_PATH or a global install).
const { chromium } = createRequire(
  process.env.PLAYWRIGHT_FROM || import.meta.url,
)("playwright");
const OUT = join(here, "..", "..", "src", "assets", "screenshots");
const SITE = process.env.SITE || "http://demo.localhost:8000";
const USER = process.env.USER_NAME || "Administrator";
const PASS = process.env.PASS || "admin";
const COMPANY = process.env.COMPANY || "Example Contracting Co.";
const only = process.argv.slice(2);
const { shots } = JSON.parse(readFileSync(join(here, "shots.json"), "utf8"));

// API calls use token auth (API_TOKEN="key:secret" of the demo user) so they never depend on the browser session.
let apiCtx;
async function api(_ctx, method, args) {
  const r = await apiCtx.post(`${SITE}/api/method/${method}`, { data: args });
  if (!r.ok()) throw new Error(`${method}: ${r.status()} ${await r.text()}`);
  return (await r.json()).message;
}

async function latest(ctx, doctype, filters = {}) {
  const rows = await api(ctx, "frappe.client.get_list", {
    doctype,
    filters,
    fields: ["name"],
    order_by: "creation desc",
    limit_page_length: 1,
  });
  return rows[0]?.name;
}

async function resolve(ctx) {
  const map = { company: encodeURIComponent(COMPANY) };
  const eq = await api(ctx, "frappe.client.get_list", {
    doctype: "Card Equipment",
    fields: ["name", "equipment_name"],
    limit_page_length: 100,
  });
  for (const e of eq) {
    const code = (e.equipment_name.match(/\(([^)]+)\)/) || [])[1];
    if (!code) continue;
    map[`eq:${code}`] = e.name;
    map[`asg:${code}`] = await latest(ctx, "Card Equipment Assignment", {
      equipment: e.name,
    });
    map[`card:${code}`] = await latest(ctx, "Card Monthly Card", {
      equipment: e.name,
    });
  }
  for (const [k, dt] of Object.entries({
    trn: "Equipment Transport",
    etc: "Employee Tool Custody",
    cdl: "Card Daily Log",
    cra: "Card Rate Agreement",
    dsl: "Project Diesel Fill",
    emr: "Equipment Meter Reading",
    enr: "Equipment Needs Request",
  }))
    map[k] = await latest(ctx, dt);
  return map;
}

function fill(path, map) {
  return path.replace(/\{([^}]+)\}/g, (_, k) => {
    if (!(k in map) || !map[k]) throw new Error(`no value for {${k}}`);
    return k === "company" ? map[k] : encodeURIComponent(map[k]);
  });
}

async function settle(page) {
  await page
    .waitForLoadState("networkidle", { timeout: 20000 })
    .catch(() => {});
  // wait until grids, number cards and charts stop showing loading skeletons
  await page
    .waitForFunction(
      () =>
        !document.querySelector(
          ".grid-row .ghost-row, .skeleton, .widget .loading, .frappe-loading",
        ),
      null,
      { timeout: 8000 },
    )
    .catch(() => {});
  await page.waitForTimeout(3000);
  // close dialogs, toasts and the "what's new" style popups so every shot is clean
  await page.keyboard.press("Escape").catch(() => {});
  await page
    .evaluate(() => {
      document
        .querySelectorAll(
          "#alert-container, .desk-alert, .toast, .frappe-toast",
        )
        .forEach((e) => e.remove());
      document
        .querySelectorAll(".modal.show")
        .forEach((m) => m.classList.remove("show"));
      document.querySelectorAll(".modal-backdrop").forEach((e) => e.remove());
      document.body.classList.remove("modal-open");
    })
    .catch(() => {});
  await page.waitForTimeout(300);
}

async function scrollToText(page, texts) {
  for (const t of texts) {
    const ok = await page.evaluate((t) => {
      const els = [
        ...document.querySelectorAll(
          "h1,h2,h3,h4,h5,.section-head,.widget-title,.form-section .section-head,label,.control-label,.ce-header",
        ),
      ];
      const el = els.find(
        (e) =>
          e.offsetParent &&
          e.textContent.trim().toLowerCase().includes(t.toLowerCase()),
      );
      if (!el) return false;
      el.scrollIntoView({ block: "start" });
      return true;
    }, t);
    if (ok) return true;
  }
  return false;
}

async function clickText(page, texts) {
  for (const t of texts) {
    const loc = page.getByText(t, { exact: false }).first();
    if (await loc.isVisible().catch(() => false)) {
      await loc.click().catch(() => {});
      await page.waitForTimeout(1200);
      return true;
    }
  }
  return false;
}

async function run() {
  const browser = await chromium.launch();
  const { request } = createRequire(
    process.env.PLAYWRIGHT_FROM || import.meta.url,
  )("playwright");
  apiCtx = await request.newContext({
    extraHTTPHeaders: { Authorization: `token ${process.env.API_TOKEN}` },
  });
  const results = [];
  for (const lang of ["en", "ar"]) {
    const ctx = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
      locale: lang,
    });
    const login = await ctx.request.post(`${SITE}/api/method/login`, {
      data: { usr: USER, pwd: PASS },
    });
    if (!login.ok()) throw new Error(`login failed: ${login.status()}`);
    await api(ctx, "frappe.client.set_value", {
      doctype: "User",
      name: USER,
      fieldname: "language",
      value: lang,
    });
    const map = await resolve(ctx);
    const mctx = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 3,
      isMobile: true,
      hasTouch: true,
      locale: lang,
      storageState: await ctx.storageState(),
    });
    // operator context for CARD Mobile and the needs page (a user linked to an Employee)
    const octx = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
      locale: lang,
    });
    const olog = await octx.request.post(`${SITE}/api/method/login`, {
      data: {
        usr: process.env.OPERATOR || "operator@example.com",
        pwd: process.env.OPERATOR_PASS || "Demo-Pass-2026",
      },
    });
    if (!olog.ok()) throw new Error(`operator login failed: ${olog.status()}`);
    await api(ctx, "frappe.client.set_value", {
      doctype: "User",
      name: process.env.OPERATOR || "operator@example.com",
      fieldname: "language",
      value: lang,
    });
    const omctx = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 3,
      isMobile: true,
      hasTouch: true,
      locale: lang,
      storageState: await octx.storageState(),
    });
    mkdirSync(join(OUT, lang), { recursive: true });
    for (const s of shots) {
      if (only.length && !only.includes(s.name)) continue;
      const op = s.as === "operator";
      const page = await (s.mobile
        ? op
          ? omctx
          : mctx
        : op
          ? octx
          : ctx
      ).newPage();
      try {
        if (s.lang && s.lang !== lang)
          await api(ctx, "frappe.client.set_value", {
            doctype: "User",
            name: USER,
            fieldname: "language",
            value: s.lang,
          });
        await page.goto(SITE + fill(s.path, map), {
          waitUntil: "domcontentloaded",
          timeout: 60000,
        });
        await settle(page);
        if (s.click) {
          await page
            .locator(s.click)
            .first()
            .click({ timeout: 3000 })
            .catch(() => {});
          await page.waitForTimeout(900);
        }
        if (s.clickText) await clickText(page, s.clickText);
        // Frappe v16 scrolls an inner container, not the window: bring every grid into view once so lazy
        // rows render, then return to the top.
        await page.evaluate(async () => {
          const grids = [
            ...document.querySelectorAll(
              ".form-grid, .grid-body, .dt-scrollable, .widget",
            ),
          ];
          for (const g of grids) {
            g.scrollIntoView({ block: "center" });
            await new Promise((r) => setTimeout(r, 400));
          }
          // reset every scrolled container (the desk scrolls an inner element) and the window
          for (const e of document.querySelectorAll("*"))
            if (e.scrollTop > 0) e.scrollTop = 0;
          window.scrollTo(0, 0);
        });
        await page.waitForTimeout(1200);
        if (s.setSelect) {
          await page.evaluate(({ from, to }) => {
            const sel = [...document.querySelectorAll("select")].find(
              (x) => x.value === from,
            );
            if (sel) {
              sel.value = to;
              sel.dispatchEvent(new Event("change", { bubbles: true }));
            }
          }, s.setSelect);
          await page.waitForTimeout(2500);
        }
        if (s.scrollSel)
          await page.evaluate((sel) => {
            const el = document.querySelector(sel);
            if (el) el.scrollIntoView({ block: "start" });
          }, s.scrollSel);
        if (s.scrollText) await scrollToText(page, s.scrollText);
        if (typeof s.scroll === "number")
          await page.evaluate((y) => {
            // scroll the largest scrollable element (the desk's main column), or the window
            const els = [
              document.scrollingElement,
              ...document.querySelectorAll("*"),
            ].filter(
              (e) =>
                e &&
                e.scrollHeight > e.clientHeight + 20 &&
                getComputedStyle(e).overflowY !== "visible",
            );
            const main = els.sort(
              (a, b) =>
                b.clientHeight * b.clientWidth - a.clientHeight * a.clientWidth,
            )[0];
            if (main) main.scrollTop = y;
            else window.scrollTo(0, y);
          }, s.scroll);
        await page.waitForTimeout(500);
        const png = await page.screenshot({ type: "png" });
        const file = join(OUT, lang, `${s.name}.webp`);
        await sharp(png).webp({ quality: 82 }).toFile(file);
        results.push(`ok   ${lang}/${s.name}`);
      } catch (e) {
        results.push(
          `FAIL ${lang}/${s.name}: ${String(e.message).slice(0, 200)}`,
        );
      } finally {
        if (s.lang && s.lang !== lang)
          await api(ctx, "frappe.client.set_value", {
            doctype: "User",
            name: USER,
            fieldname: "language",
            value: lang,
          });
        await page.close();
      }
    }
    await mctx.close();
    await omctx.close();
    await octx.close();
    await ctx.close();
  }
  await browser.close();
  console.log(results.join("\n"));
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
