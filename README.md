<!doctype html><meta charset="utf-8">
<style>
body{max-width:900px;margin:24px auto;padding:0 32px;font:16px/1.6 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1f2328;background:#fff}
h1,h2{border-bottom:1px solid #d1d9e0;padding-bottom:.3em;font-weight:600}
h2{font-size:1.4em;margin-top:28px} h3{font-size:1.1em}
code{background:#eff1f3;padding:2px 6px;border-radius:6px;font-size:85%}
pre{background:#f6f8fa;padding:14px;border-radius:8px;overflow:auto} pre code{background:none;padding:0}
table{border-collapse:collapse} td,th{border:1px solid #d1d9e0;padding:6px 13px}
img{vertical-align:middle} a{color:#0969da;text-decoration:none} div[align=center]{text-align:center}
</style>
<div align="center">
	<a target="_blank" rel="noopener noreferrer" href="card/public/images/card-logo.svg"><svg width="72" height="72" viewBox="0 0 54 54" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M38.5714 0H15.4286C6.90761 0 0 6.90761 0 15.4286V38.5714C0 47.0924 6.90761 54 15.4286 54H38.5714C47.0924 54 54 47.0924 54 38.5714V15.4286C54 6.90761 47.0924 0 38.5714 0Z" fill="#06B58B" fill-opacity="0.1"/>
<g stroke="#1F876C" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">
<path d="M21 40.5H14.5C13.4 40.5 12.5 39.6 12.5 38.5V14.5C12.5 13.4 13.4 12.5 14.5 12.5H31.5C32.6 12.5 33.5 13.4 33.5 14.5V23"/>
<path d="M18 20.5H28"/>
<path d="M18 26.5H24"/>
</g>
<rect x="17.5" y="9.5" width="11" height="6" rx="2" fill="#1F876C"/>
<g fill="#1F876C">
<path d="M22.5 33H28.5L29.5 42H23.5Z"/>
<path d="M28 35.6L33.4 32.6L34.6 35.4L29.2 38.4Z"/>
<rect x="32" y="34.5" width="14" height="7" rx="1.6"/>
<path d="M37 26H43.5C44.3 26 45 26.7 45 27.5V35H35.5V27.5C35.5 26.7 36.2 26 37 26Z"/>
<circle cx="35.5" cy="43.2" r="3.3"/>
<circle cx="42.7" cy="43.2" r="3.3"/>
</g>
<rect x="38" y="28.4" width="4.6" height="3.6" rx="0.8" fill="#E6F7F3"/>
</svg></a>
	<h2>CARD</h2>
	<p><b>Monthly equipment operation cards for ERPNext</b><br>
	Track rented and owned equipment, daily working hours and monthly amounts, with supplier reconciliation against the General Ledger and an Arabic (RTL) interface.</p>
<p><a href="https://github.com/SDe-ER/card/actions/workflows/ci.yml"><img src="https://github.com/SDe-ER/card/actions/workflows/ci.yml/badge.svg" alt="CI" style="max-width: 100%;"></a><br>
<a href="https://github.com/SDe-ER/card/releases"><img src="https://camo.githubusercontent.com/2f0bf0a6506fa4adfdc4797b05ee847a1042ca5d5e2f893d4bf998d8f4d30f23/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f72656c656173652d76312e302e312d303642353842" alt="Release" data-canonical-src="https://img.shields.io/badge/release-v1.0.1-06B58B" style="max-width: 100%;"></a><br>
<a href="license.txt"><img src="https://camo.githubusercontent.com/b8cadaa967891081f8f165695470689986c028821dd8a040132f6e661795dc0d/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6c6963656e73652d4d49542d626c7565" alt="License: MIT" data-canonical-src="https://img.shields.io/badge/license-MIT-blue" style="max-width: 100%;"></a><br>
<a href="https://frappeframework.com" rel="nofollow"><img src="https://camo.githubusercontent.com/d0c7750463756914ff50ae4bfd85e9d781e33f60f8dc66cd940a3a4296e982e0/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6672617070652d25453225383925413525323031362e35302d314638373643" alt="Frappe" data-canonical-src="https://img.shields.io/badge/frappe-%E2%89%A5%2016.50-1F876C" style="max-width: 100%;"></a></p>
</div>

<h2>What is CARD</h2>
<p>CARD is a standalone <a href="https://frappeframework.com" rel="nofollow">Frappe</a> v16 app that manages <strong>monthly equipment operation cards</strong> and <strong>supplier reconciliation</strong> for contracting and equipment-rental operations. It is <strong>built on the Frappe Framework</strong> and requires <strong>ERPNext</strong> for the shared company, supplier and accounting backbone.</p>
<p>It packages a set of equipment DocTypes, the monthly-card workflow, two script reports, and a <em>Card</em> workspace with an app-owned desktop icon — all installable on any Frappe v16 site with a single <code class="notranslate">install-app</code>.</p>
<h2>Key features</h2>
<ul>
<li><strong>Equipment registry</strong> — DocTypes for equipment, categories, types, suppliers and equipment assignments.</li>
<li><strong>Monthly operation cards</strong> — record hours worked per day; the monthly amount = total working hours × approved hourly rate.</li>
<li><strong>Rate derivation</strong> — the hourly rate is derived from the daily rate ÷ the daily hours; owned equipment (<code class="notranslate">ملك</code>) carries an amount of 0 (hours only).</li>
<li><strong>Adjustments</strong> — a child table of additions/deductions produces the net monthly amount.</li>
<li><strong>Supplier reconciliation</strong> — <em>Equipment Suppliers Summary</em> and <em>Equipment Supplier Statement</em> reports reconcile card totals against supplier GL entries (accrual credits / payment debits, opening/closing, matching difference).</li>
<li><strong>Desk workspace</strong> — a <em>Card</em> workspace (number cards, dashboard chart, shortcuts) and a single app-owned desktop icon with the CARD logo.</li>
<li><strong>Arabic (RTL) UI</strong> — labels and layout designed for right-to-left use; the monthly print format is <code class="notranslate">كارت تشغيل شهري</code>.</li>
</ul>
<h2>Screenshots</h2>
<blockquote>
<p>UI screenshots are captured on a throwaway demo site seeded with <strong>fake data only</strong> and stored under <code class="notranslate">.github/images/</code>. They are added in a follow-up commit on this branch — <strong>no real company, supplier, operator, project or financial data is ever committed.</strong></p>
</blockquote>
<h2>Under the hood</h2>
<ul>
<li><a href="https://frappeframework.com" rel="nofollow"><strong>Frappe Framework</strong></a> — the full-stack Python/JavaScript web framework CARD is built on (database layer, auth, REST API, Desk UI). <em>Dependency.</em></li>
<li><a href="https://github.com/frappe/erpnext"><strong>ERPNext</strong></a> — provides Company, Cost Center, Project, Supplier, Asset and the General Ledger that CARD reconciles against. <em>Required app.</em></li>
<li><a href="https://github.com/frappe/hrms"><strong>Frappe HR (HRMS)</strong></a> — Employee links used by equipment assignments. <em>Optional at runtime.</em></li>
</ul>
<p>CARD links only to standard Frappe/ERPNext/HR doctypes and its own doctypes — it has <strong>no dependency on any other custom app</strong>.</p>
<h2>Compatibility</h2>
<markdown-accessiblity-table><table role="table">
<thead>
<tr>
<th></th>
<th>Version</th>
</tr>
</thead>
<tbody>
<tr>
<td>Frappe</td>
<td><strong>≥ 16.50</strong> (validated on 16.51.1; v1.0.1+ required for ≥ 16.51)</td>
</tr>
<tr>
<td>ERPNext</td>
<td><strong>v16</strong> (required app)</td>
</tr>
<tr>
<td>Frappe HR</td>
<td><strong>v16</strong> (optional)</td>
</tr>
<tr>
<td>Python</td>
<td><strong>3.14</strong></td>
</tr>
</tbody>
</table></markdown-accessiblity-table>
<h2>Installation</h2>
<h3>Fresh site (bench)</h3>
<div class="highlight highlight-source-shell"><pre class="notranslate"><span class="pl-c1">cd</span> <span class="pl-smi">$PATH_TO_YOUR_BENCH</span>
bench get-app <span class="pl-smi">$URL_OF_THIS_REPO</span> --branch version-16
bench --site <span class="pl-k">&lt;</span>site<span class="pl-k">&gt;</span> install-app card
bench --site <span class="pl-k">&lt;</span>site<span class="pl-k">&gt;</span> migrate</pre></div>
<h3>Site that already has a legacy custom Module Def "Card"</h3>
<p>If the site already carries a custom Module Def named <code class="notranslate">Card</code> (e.g. a setup built with client/server scripts before this app existed), install with <code class="notranslate">--force</code>. The installer <strong>adopts</strong> the existing Module Def (re-points it to this app, <code class="notranslate">custom=0</code>) and never deletes it — deleting it would cascade-delete the data. It also, idempotently: flips the 8 Card DocTypes to <code class="notranslate">custom=0 / module=Card</code>, creates the <code class="notranslate">default_print_format</code> Property Setter, disables (never deletes) the legacy server/client scripts, ensures exactly one app-owned desktop icon, folds the frappe-16.50 navigation sidebar into the canonical <code class="notranslate">Card</code> one, and appends the Card launcher to each entitled user's desktop layout (append-only).</p>
<div class="highlight highlight-source-shell"><pre class="notranslate">bench --site <span class="pl-k">&lt;</span>site<span class="pl-k">&gt;</span> install-app card --force
bench --site <span class="pl-k">&lt;</span>site<span class="pl-k">&gt;</span> migrate</pre></div>
<h3>Baked into a Docker image (production)</h3>
<p>Where Frappe apps are baked into the image rather than fetched on the host, add CARD from a verified source archive of the tag and install it inside the running backend container:</p>
<div class="highlight highlight-source-dockerfile"><pre class="notranslate"><span class="pl-c"><span class="pl-c">#</span> add on top of your existing Frappe/ERPNext v16 image</span>
<span class="pl-k">COPY</span> --chown=frappe:frappe card-src /home/frappe/frappe-bench/apps/card
<span class="pl-k">RUN</span> env/bin/pip install --no-cache-dir -e apps/card \
 &amp;&amp; bench build --app card \
 &amp;&amp; mkdir -p assets/card &amp;&amp; cp -aL apps/card/card/public/. assets/card/ \
 &amp;&amp; rm -rf sites/assets</pre></div>
<blockquote>
<p><strong>Asset note:</strong> if your runtime mounts <code class="notranslate">sites/</code> as a volume whose <code class="notranslate">sites/assets</code> is a symlink to the image's <code class="notranslate">assets/</code> directory, CARD's static files must live in the image's bench-root <code class="notranslate">assets/card</code> (as above) — otherwise the volume masks them and <code class="notranslate">/assets/card/...</code> 404s.</p>
</blockquote>
<p>Then, inside the backend container, ensure <code class="notranslate">card</code> is listed in <code class="notranslate">sites/apps.txt</code> and run <code class="notranslate">install-app card [--force]</code> + <code class="notranslate">migrate</code>.</p>
<h2>Development setup</h2>
<div class="highlight highlight-source-shell"><pre class="notranslate"><span class="pl-c"><span class="pl-c">#</span> inside an existing bench with frappe &gt;=16.50 and erpnext v16</span>
bench get-app /path/to/card
bench --site <span class="pl-k">&lt;</span>dev-site<span class="pl-k">&gt;</span> install-app card
<span class="pl-c1">cd</span> apps/card <span class="pl-k">&amp;&amp;</span> pre-commit install</pre></div>
<p>Run the tests:</p>
<div class="highlight highlight-source-shell"><pre class="notranslate">bench --site <span class="pl-k">&lt;</span>site<span class="pl-k">&gt;</span> run-tests --app card</pre></div>
<p>The suite covers the controllers plus install / desktop-icon / sidebar-fold / idempotency behaviour.</p>
<h2>Contributing</h2>
<p>Contributions are welcome. Please read <a href="CONTRIBUTING.md">CONTRIBUTING.md</a> and our <a href="CODE_OF_CONDUCT.md">Code of Conduct</a>. This app uses <code class="notranslate">pre-commit</code> (ruff, ruff-format, prettier) and conventional PR titles.</p>
<h2>Security</h2>
<p>Please report security issues privately to <strong><a href="mailto:info@sdce.sa">info@sdce.sa</a></strong> — see <a href="SECURITY.md">SECURITY.md</a>. Do not open public issues for vulnerabilities.</p>
<h2>Release history</h2>
<p>See <a href="CHANGELOG.md">CHANGELOG.md</a> and the <a href="https://github.com/SDe-ER/card/releases">Releases</a> page.</p>
<h2>License</h2>
<p><a href="license.txt">MIT</a> © 2026 Shams Dubai Contracting Est. (SDCE). Contact: <a href="mailto:info@sdce.sa">info@sdce.sa</a></p>
<h2>Logo and Trademark Policy</h2>
<p>The <strong>CARD</strong> name and the CARD logo are © Shams Dubai Contracting Est. (SDCE).</p>
<p>CARD is an independent application developed by SDCE and is <strong>built on the Frappe Framework</strong>. CARD is <strong>not</strong> a product of, and is <strong>not</strong> endorsed, sponsored or maintained by Frappe Technologies Pvt. Ltd. "Frappe", "Frappe Framework", "ERPNext" and "Frappe HR" are trademarks of Frappe Technologies Pvt. Ltd., referenced here only to identify the framework and the applications CARD depends on. Use of those names does not imply any affiliation or endorsement, and this project follows the <a href="https://github.com/frappe/erpnext/blob/develop/TRADEMARK_POLICY.md">ERPNext Logo and Trademark Policy</a>. No Frappe or ERPNext logos or wordmarks are used as CARD's own branding.</p>
<div align="center">
	<a target="_blank" rel="noopener noreferrer" href="card/public/images/card-logo.svg"><svg width="72" height="72" viewBox="0 0 54 54" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M38.5714 0H15.4286C6.90761 0 0 6.90761 0 15.4286V38.5714C0 47.0924 6.90761 54 15.4286 54H38.5714C47.0924 54 54 47.0924 54 38.5714V15.4286C54 6.90761 47.0924 0 38.5714 0Z" fill="#06B58B" fill-opacity="0.1"/>
<g stroke="#1F876C" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">
<path d="M21 40.5H14.5C13.4 40.5 12.5 39.6 12.5 38.5V14.5C12.5 13.4 13.4 12.5 14.5 12.5H31.5C32.6 12.5 33.5 13.4 33.5 14.5V23"/>
<path d="M18 20.5H28"/>
<path d="M18 26.5H24"/>
</g>
<rect x="17.5" y="9.5" width="11" height="6" rx="2" fill="#1F876C"/>
<g fill="#1F876C">
<path d="M22.5 33H28.5L29.5 42H23.5Z"/>
<path d="M28 35.6L33.4 32.6L34.6 35.4L29.2 38.4Z"/>
<rect x="32" y="34.5" width="14" height="7" rx="1.6"/>
<path d="M37 26H43.5C44.3 26 45 26.7 45 27.5V35H35.5V27.5C35.5 26.7 36.2 26 37 26Z"/>
<circle cx="35.5" cy="43.2" r="3.3"/>
<circle cx="42.7" cy="43.2" r="3.3"/>
</g>
<rect x="38" y="28.4" width="4.6" height="3.6" rx="0.8" fill="#E6F7F3"/>
</svg></a>
</div>
