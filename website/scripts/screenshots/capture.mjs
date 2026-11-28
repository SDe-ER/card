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
// SKIP_PREFIX leaves out the shots whose name starts with it; ONLY_PREFIX keeps only those. The workflow takes the
// invoice shots in a second pass, after it has seeded the invoices that the first pass must not see.
const skipPrefix = process.env.SKIP_PREFIX;
const onlyPrefix = process.env.ONLY_PREFIX;
const { shots } = JSON.parse(readFileSync(join(here, "shots.json"), "utf8"));

// API calls go through the demo user's logged-in session (set after login in run()).
let apiCtx;
// A page showing the Desk welcome screen or the "not configured" screen is a defect: the shot fails, no image is written.
const DEFECT =
  /Get Started|Let's give your business a home|not set up to ask for equipment needs|غير مهيأ لطلب/;
// A number card is captured alone. It is found first by its record name, which Frappe writes to the widget as
// data-widget-name and which does not change with the language. The translated label from the app's own locale
// file (read at run time, never hard-coded) is the fallback. The shot waits until the card body shows a value
// that is not zero: the title is not read, and a card that stays at 0 has no data behind it.
// No match or no value is a failed shot, never a page-sized image.
const LOCALE_DIR = join(here, "..", "..", "..", "card", "locale");
function translatedLabel(lang, msgid) {
  if (lang === "en") return msgid;
  const po = readFileSync(join(LOCALE_DIR, `${lang}.po`), "utf8");
  const head = `msgid "${msgid}"\nmsgstr "`;
  const at = po.indexOf(head);
  if (at < 0) return null;
  const start = at + head.length;
  return po.slice(start, po.indexOf('"', start));
}
async function elementShot(page, lang, name) {
  const candidates = [page.locator(`.widget[data-widget-name="${name}"]`)];
  const label = translatedLabel(lang, name);
  if (label)
    candidates.push(
      page
        .locator(".widget")
        .filter({ hasText: label })
        .filter({ hasNot: page.locator(".widget") }),
    );
  for (const base of candidates) {
    const loc = base.first();
    if ((await loc.count()) === 0) continue;
    await loc.scrollIntoViewIfNeeded();
    await page.waitForFunction(
      (el) =>
        /[1-9\u0661-\u0669]/.test(
          (el.querySelector(".widget-body") || el).innerText || "",
        ),
      await loc.elementHandle(),
      {
        timeout: 30000,
      },
    );
    return loc.screenshot({ type: "png" });
  }
  throw new Error(`no number card "${name}" (label ${label ?? "n/a"})`);
}
// Session POSTs need Frappe's CSRF token; it is read from the logged-in desk page once per session.
let csrfToken = null;
async function getCsrf() {
  if (!csrfToken) {
    const html = await (await apiCtx.get(`${SITE}/app`)).text();
    const m = html.match(/csrf_token["'\s:=]+["']([^"']{16,})["']/);
    if (!m) throw new Error("csrf token not found on /app");
    csrfToken = m[1];
  }
  return csrfToken;
}

async function api(_ctx, method, args) {
  const r = await apiCtx.post(`${SITE}/api/method/${method}`, {
    data: args,
    headers: { "X-Frappe-CSRF-Token": await getCsrf() },
  });
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
  // the two fictitious invoices of ci_link_invoices.py (the Desk-button shots)
  map["si:unlinked"] = await latest(ctx, "Sales Invoice", {
    remarks: "Card demo - unlinked invoice",
  });
  map["si:linked"] = await latest(ctx, "Sales Invoice", {
    remarks: "Card demo - linked invoice",
  });
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

// A report shot shows the result of the Desk call frappe.desk.query_report.run. Desk continues only when that call
// succeeds (frappe version-16 query_report.js, refresh: "callback: resolve"). When the server refuses the run, the
// page keeps its "Loading..." screen and the error is in a dialog, which settle() closes. Run 45859674403 saved
// that screen as the image of two reports. The answers of the call are recorded per page, and a report shot is
// taken only when the last run succeeded, the loading screen is gone and the page shows rows, a summary or the
// "nothing to show" message. Anything else is a failed shot that names the HTTP status and the server message.
const REPORT_RUN = "/api/method/frappe.desk.query_report.run";
const REPORT_TIMEOUT = 30000;
const isReport = (path) =>
  path.startsWith("/app/query-report/") ||
  path.startsWith("/desk/query-report/");

function serverMessage(body) {
  try {
    const r = JSON.parse(body);
    const messages = JSON.parse(r._server_messages || "[]").map(
      (m) => JSON.parse(m).message,
    );
    return [r.exc_type, ...messages]
      .filter(Boolean)
      .join(": ")
      .replace(/<[^>]*>/g, " ")
      .slice(0, 140);
  } catch {
    return "";
  }
}

function watchReportRuns(page) {
  const runs = [];
  page.on("response", (r) => {
    if (!r.url().includes(REPORT_RUN)) return;
    runs.push({
      status: r.status(),
      message: r.ok()
        ? ""
        : r
            .text()
            .then(serverMessage)
            .catch(() => ""),
    });
  });
  // a call that never gets an answer (network error, abort) has no status; its error text names the cause
  page.on("requestfailed", (r) => {
    if (!r.url().includes(REPORT_RUN)) return;
    // an aborted call (a late request cut by the page) must not fail a report that drew
    if (r.failure()?.errorText === "net::ERR_ABORTED") return;
    runs.push({
      status: 0,
      message: Promise.resolve(r.failure()?.errorText ?? ""),
    });
  });
  return runs;
}

function reportDrawn() {
  const report = window.frappe?.query_report;
  if (!report || report.$loading?.is(":visible")) return false;
  return (
    report.$report.find(".dt-row:visible").length > 0 ||
    report.$summary.is(":visible") ||
    report.$message.is(":visible")
  );
}

async function reportReady(page, runs) {
  const deadline = Date.now() + REPORT_TIMEOUT;
  for (;;) {
    const last = runs.at(-1);
    if (last && (last.status >= 400 || last.status === 0)) {
      const cause = last.status ? `HTTP ${last.status}` : "request failed";
      throw new Error(`report run failed: ${cause} ${await last.message}`);
    }
    if (last && (await page.evaluate(reportDrawn))) return;
    if (Date.now() > deadline)
      throw new Error(last ? "report still loading" : "report did not run");
    await page.waitForTimeout(250);
  }
}

// A screenshot of one flat colour shows no screen at all (run 45656288398 wrote plain white Arabic pages).
async function isBlank(png) {
  const { channels } = await sharp(png).stats();
  return channels.every((c) => c.min === c.max);
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
      await loc.click({ timeout: 3000 });
      await page.waitForTimeout(1200);
      return true;
    }
  }
  return false;
}

async function run() {
  const browser = await chromium.launch();
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
    // API calls reuse this logged-in session, so no API key pair is needed.
    apiCtx = ctx.request;
    csrfToken = null;
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
      if (skipPrefix && s.name.startsWith(skipPrefix)) continue;
      if (onlyPrefix && !s.name.startsWith(onlyPrefix)) continue;
      const op = s.as === "operator";
      const page = await (s.mobile
        ? op
          ? omctx
          : mctx
        : op
          ? octx
          : ctx
      ).newPage();
      const reportRuns = isReport(s.path) ? watchReportRuns(page) : null;
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
        const landed = page.url();
        const bodyText = await page.evaluate(
          () => document.body.innerText || "",
        );
        console.log(`[route] ${lang}/${s.name} -> ${landed}`);
        if (DEFECT.test(bodyText))
          throw new Error(`defect screen at ${landed}`);
        // a missing or failing click is a failed shot, never a silently unchanged page
        if (s.click) {
          await page.locator(s.click).first().click({ timeout: 3000 });
          await page.waitForTimeout(900);
        }
        // a collapsible form section is opened by its fieldname; one that is already open is left alone
        if (s.expandSection) {
          const sel = `.form-section[data-fieldname="${s.expandSection}"] .section-head`;
          await page.locator(sel).first().waitFor({ timeout: 15000 });
          const closed = page.locator(`${sel}.collapsed`).first();
          if (await closed.count()) {
            await closed.click({ timeout: 3000 });
            await page.waitForTimeout(900);
          }
        }
        if (s.clickText && !(await clickText(page, s.clickText)))
          throw new Error(
            `no visible element for click: ${s.clickText.join(" / ")}`,
          );
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
        // setSelect redraws the page body, so a click on what it draws comes after it
        if (s.clickTextAfter && !(await clickText(page, s.clickTextAfter)))
          throw new Error(
            `no visible element for click: ${s.clickTextAfter.join(" / ")}`,
          );
        // ordered clicks after the text clicks: a string is a CSS selector, an array is a list of texts (the first
        // one that is visible is clicked); a step that finds nothing fails the shot (a menu item, a dialog check box)
        for (const step of s.clickSteps || []) {
          if (Array.isArray(step)) {
            if (!(await clickText(page, step)))
              throw new Error(
                `no visible element for click: ${step.join(" / ")}`,
              );
          } else {
            await page.locator(step).first().click({ timeout: 3000 });
            await page.waitForTimeout(500);
          }
        }
        // a click on each selector in turn, after the text clicks (for example the check boxes of a dialog)
        for (const sel of s.clickSelAfter || []) {
          await page.locator(sel).first().click({ timeout: 3000 });
          await page.waitForTimeout(500);
        }
        if (reportRuns) await reportReady(page, reportRuns);
        // what the shot is about must be on screen: a panel that did not open or a report with no rows is a failed shot
        if (s.waitSel)
          await page
            .locator(s.waitSel)
            .first()
            .waitFor({ state: "visible", timeout: 15000 });
        if (s.scrollSel) {
          const found = await page.evaluate(
            ({ sel, block }) => {
              const el = document.querySelector(sel);
              if (!el || !el.offsetParent) return false;
              el.scrollIntoView({ block });
              return true;
            },
            { sel: s.scrollSel, block: s.scrollBlock || "start" },
          );
          if (!found)
            throw new Error(`no element to scroll to: ${s.scrollSel}`);
        }
        if (s.scrollText && !(await scrollToText(page, s.scrollText)))
          throw new Error(
            `no section to scroll to: ${s.scrollText.join(" / ")}`,
          );
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
        const png = s.elementName
          ? await elementShot(page, lang, s.elementName)
          : await page.screenshot({ type: "png" });
        if (await isBlank(png)) throw new Error(`blank image at ${landed}`);
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
  if (results.some((r) => r.startsWith("FAIL")))
    throw new Error("one or more screenshots failed");
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
