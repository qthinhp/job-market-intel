"""Render the warehouse into a single self-contained HTML page.

Everything — data, styles, script — is inlined into one file. No CDN, no
server, no build toolchain. That means the output works three ways with no
changes: opened from disk, served by GitHub Pages, or emailed to someone.

All 5,687 postings ship with the page and are filtered client-side, so typing
in the search box is instant rather than a round trip. The payload is ~1 MB of
JSON before compression, which GitHub Pages serves gzipped at roughly a
quarter of that.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE = REPO_ROOT / "data" / "warehouse.duckdb"
DIST = Path(__file__).resolve().parent / "dist"

POSTINGS_SQL = """
select
    company_name              as company,
    title,
    job_family                as family,
    seniority_band            as seniority,
    coalesce(location_raw, '')as location,
    is_remote                 as remote,
    coalesce(compensation_summary, '') as pay,
    job_url                   as url,
    cast(published_at as date)as published,
    days_since_published      as age
from marts.dim_posting
where is_open
order by company_name, title
"""

SUMMARY_SQL = """
select
    (select count(*) from marts.dim_posting where is_open)                    as postings,
    (select count(distinct requisition_key) from marts.dim_posting where is_open) as roles,
    (select count(*) from marts.dim_company)                                  as companies,
    (select max(snapshot_date) from marts.fct_posting_snapshot)               as as_of,
    (select count(distinct snapshot_date) from marts.fct_posting_snapshot)    as snapshots,
    (select round(100.0 * avg(case when is_remote then 1 else 0 end), 0)
       from marts.dim_posting where is_open)                                  as pct_remote,
    (select round(100.0 * avg(case when has_disclosed_pay then 1 else 0 end), 0)
       from marts.dim_posting where is_open)                                  as pct_pay
"""

FAMILY_SQL = """
select job_family as family, count(*) as postings
from marts.dim_posting where is_open
group by 1 order by postings desc
"""

COMPANY_SQL = """
select company_name as company, open_postings as postings,
       pct_with_pay_disclosed as pay, pct_remote as remote
from marts.dim_company order by open_postings desc
"""

# Families worth surfacing as a one-click filter — the reason this site exists.
DATA_FAMILIES = ["analytics", "analytics engineering", "data engineering", "data science",
                 "ml engineering", "research"]


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    result = con.sql(sql)
    columns = result.columns
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def to_json(value) -> str:
    """Serialize for embedding in a <script> tag.

    Escaping '<' is what makes that safe: a job description containing the
    literal text '</script>' would otherwise terminate the tag early and break
    the page.
    """
    return (
        json.dumps(value, default=str, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def build() -> int:
    if not WAREHOUSE.exists():
        print(f"No warehouse at {WAREHOUSE} — run `python -m ingest.load`.", file=sys.stderr)
        return 1

    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    postings = rows(con, POSTINGS_SQL)
    summary = rows(con, SUMMARY_SQL)[0]
    families = rows(con, FAMILY_SQL)
    companies = rows(con, COMPANY_SQL)
    con.close()

    html = TEMPLATE.format(
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        as_of=summary["as_of"],
        postings=f"{summary['postings']:,}",
        roles=f"{summary['roles']:,}",
        companies=summary["companies"],
        snapshots=summary["snapshots"],
        pct_remote=int(summary["pct_remote"]),
        pct_pay=int(summary["pct_pay"]),
        family_options="".join(
            f'<option value="{f["family"]}">{f["family"]} ({f["postings"]})</option>'
            for f in families
        ),
        family_bars=render_bars(families, "family", "postings"),
        company_bars=render_bars(companies[:12], "company", "postings"),
        data_families=to_json(DATA_FAMILIES),
        postings_json=to_json(postings),
    )

    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / "index.html"
    out.write_text(html, encoding="utf-8")

    # GitHub Pages runs Jekyll by default, which strips files and folders whose
    # names begin with an underscore. This project has none today, but the file
    # costs nothing and prevents a genuinely baffling future bug.
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    size_kb = out.stat().st_size / 1024
    print(f"Built {out}  ({size_kb:,.0f} KB, {len(postings):,} postings)")
    return 0


def render_bars(data: list[dict], label_key: str, value_key: str) -> str:
    if not data:
        return ""
    top = max(row[value_key] for row in data) or 1
    return "".join(
        f'<div class="bar-row"><span class="bar-label">{row[label_key]}</span>'
        f'<span class="bar-track"><span class="bar-fill" style="width:{row[value_key] / top * 100:.1f}%"></span></span>'
        f'<span class="bar-value">{row[value_key]:,}</span></div>'
        for row in data
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>US Tech Job Market — job-market-intel</title>
<style>
  :root {{
    --bg:#ffffff; --panel:#f6f7f9; --border:#e2e5ea; --text:#14161a;
    --muted:#646b76; --accent:#2f6feb; --accent-soft:#e7efff;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0d1117; --panel:#161b22; --border:#2a313c; --text:#e6edf3;
      --muted:#8b949e; --accent:#4c8bf5; --accent-soft:#132038;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--bg); color:var(--text);
    font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:28px 20px 64px; }}
  header h1 {{ font-size:23px; margin:0 0 4px; letter-spacing:-.01em; }}
  header p {{ margin:0; color:var(--muted); font-size:13.5px; }}
  a {{ color:var(--accent); }}

  .tiles {{ display:grid; gap:12px; margin:24px 0;
           grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); }}
  .tile {{ background:var(--panel); border:1px solid var(--border);
          border-radius:10px; padding:14px 16px; }}
  .tile b {{ display:block; font-size:25px; font-weight:600; letter-spacing:-.02em; }}
  .tile span {{ color:var(--muted); font-size:12.5px; }}

  .panels {{ display:grid; gap:18px; grid-template-columns:1fr 1fr; margin-bottom:26px; }}
  @media (max-width:820px) {{ .panels {{ grid-template-columns:1fr; }} }}
  .panel {{ background:var(--panel); border:1px solid var(--border);
           border-radius:10px; padding:16px 18px; }}
  .panel h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.06em;
              color:var(--muted); margin:0 0 12px; font-weight:600; }}
  .bar-row {{ display:grid; grid-template-columns:150px 1fr 52px;
             align-items:center; gap:10px; margin-bottom:5px; font-size:13px; }}
  .bar-label {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .bar-track {{ background:var(--accent-soft); border-radius:4px; height:9px; }}
  .bar-fill {{ display:block; background:var(--accent); height:100%; border-radius:4px; }}
  .bar-value {{ text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; }}

  .controls {{ display:flex; flex-wrap:wrap; gap:9px; align-items:center; margin-bottom:14px; }}
  input[type=search], select {{
    background:var(--bg); color:var(--text); border:1px solid var(--border);
    border-radius:7px; padding:8px 11px; font-size:14px; font-family:inherit;
  }}
  input[type=search] {{ flex:1; min-width:220px; }}
  .chip {{ border:1px solid var(--border); background:var(--bg); color:var(--text);
          border-radius:999px; padding:7px 13px; font-size:13px; cursor:pointer;
          font-family:inherit; }}
  .chip[aria-pressed=true] {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
  .count {{ color:var(--muted); font-size:13px; margin-left:auto; }}

  .table-scroll {{ overflow-x:auto; border:1px solid var(--border); border-radius:10px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
  th, td {{ text-align:left; padding:9px 12px; border-bottom:1px solid var(--border);
           white-space:nowrap; }}
  th {{ background:var(--panel); position:sticky; top:0; cursor:pointer;
       font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
  th:hover {{ color:var(--text); }}
  tbody tr:hover {{ background:var(--panel); }}
  td.title {{ white-space:normal; min-width:280px; }}
  .tag {{ background:var(--accent-soft); color:var(--accent); border-radius:5px;
         padding:2px 7px; font-size:11.5px; white-space:nowrap; }}
  .empty {{ padding:34px; text-align:center; color:var(--muted); }}
  footer {{ margin-top:26px; color:var(--muted); font-size:12.5px; }}
</style>
</head>
<body>
<div class="wrap">

  <header>
    <h1>US Tech Job Market</h1>
    <p>{companies} companies tracked daily via public ATS APIs &middot;
       snapshot {as_of} &middot; generated {generated}</p>
  </header>

  <div class="tiles">
    <div class="tile"><b>{postings}</b><span>open postings</span></div>
    <div class="tile"><b>{roles}</b><span>distinct roles</span></div>
    <div class="tile"><b>{companies}</b><span>companies</span></div>
    <div class="tile"><b>{pct_remote}%</b><span>remote</span></div>
    <div class="tile"><b>{pct_pay}%</b><span>pay disclosed</span></div>
    <div class="tile"><b>{snapshots}</b><span>daily snapshots</span></div>
  </div>

  <div class="panels">
    <div class="panel"><h2>Postings by job family</h2>{family_bars}</div>
    <div class="panel"><h2>Top companies by openings</h2>{company_bars}</div>
  </div>

  <div class="controls">
    <input type="search" id="q" placeholder="Search title, company, or location…" autocomplete="off">
    <select id="family"><option value="">All families</option>{family_options}</select>
    <select id="seniority"><option value="">All levels</option></select>
    <button class="chip" id="dataOnly" aria-pressed="false">Data roles only</button>
    <button class="chip" id="remoteOnly" aria-pressed="false">Remote</button>
    <button class="chip" id="payOnly" aria-pressed="false">Pay shown</button>
    <span class="count" id="count"></span>
  </div>

  <div class="table-scroll">
    <table>
      <thead><tr>
        <th data-sort="company">Company</th>
        <th data-sort="title">Title</th>
        <th data-sort="family">Family</th>
        <th data-sort="seniority">Level</th>
        <th data-sort="location">Location</th>
        <th data-sort="pay">Pay</th>
        <th data-sort="age">Age</th>
      </tr></thead>
      <tbody id="rows"></tbody>
    </table>
    <div class="empty" id="empty" hidden>No postings match those filters.</div>
  </div>

  <footer>
    Data from public Greenhouse and Ashby job board APIs. Rebuilt daily by GitHub Actions.
    <a href="https://github.com/qthinhp/job-market-intel">Source</a>
  </footer>
</div>

<script id="postings" type="application/json">{postings_json}</script>
<script id="datafams" type="application/json">{data_families}</script>
<script>
const ALL  = JSON.parse(document.getElementById('postings').textContent);
const DATA = new Set(JSON.parse(document.getElementById('datafams').textContent));

const $ = id => document.getElementById(id);
const state = {{ sort:'company', dir:1 }};

// Levels come from the data rather than a hardcoded list, so the filter can
// never drift out of sync with the model.
const LEVEL_ORDER = ['intern','entry','mid','senior','staff+','executive','unspecified'];
const levels = [...new Set(ALL.map(p => p.seniority))]
  .sort((a,b) => LEVEL_ORDER.indexOf(a) - LEVEL_ORDER.indexOf(b));
$('seniority').insertAdjacentHTML('beforeend',
  levels.map(l => `<option value="${{l}}">${{l}}</option>`).join(''));

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);

function filtered() {{
  const q = $('q').value.trim().toLowerCase();
  const fam = $('family').value, sen = $('seniority').value;
  const dataOnly   = $('dataOnly').getAttribute('aria-pressed') === 'true';
  const remoteOnly = $('remoteOnly').getAttribute('aria-pressed') === 'true';
  const payOnly    = $('payOnly').getAttribute('aria-pressed') === 'true';

  let out = ALL.filter(p =>
    (!fam || p.family === fam) &&
    (!sen || p.seniority === sen) &&
    (!dataOnly   || DATA.has(p.family)) &&
    (!remoteOnly || p.remote) &&
    (!payOnly    || p.pay) &&
    (!q || (p.title + ' ' + p.company + ' ' + p.location).toLowerCase().includes(q))
  );

  const k = state.sort;
  out.sort((a, b) => {{
    const x = a[k], y = b[k];
    if (typeof x === 'number' && typeof y === 'number') return (x - y) * state.dir;
    return String(x).localeCompare(String(y)) * state.dir;
  }});
  return out;
}}

function render() {{
  const list = filtered();
  $('count').textContent = `${{list.length.toLocaleString()}} of ${{ALL.length.toLocaleString()}}`;
  $('empty').hidden = list.length > 0;

  // Capped for responsiveness: 5,000 <tr> elements makes typing feel laggy.
  // The count above always reflects the true total.
  $('rows').innerHTML = list.slice(0, 400).map(p => `
    <tr>
      <td>${{esc(p.company)}}</td>
      <td class="title"><a href="${{esc(p.url)}}" target="_blank" rel="noopener">${{esc(p.title)}}</a></td>
      <td><span class="tag">${{esc(p.family)}}</span></td>
      <td>${{esc(p.seniority)}}</td>
      <td>${{p.remote ? '&#127758; ' : ''}}${{esc(p.location)}}</td>
      <td>${{esc(p.pay)}}</td>
      <td>${{p.age == null ? '' : p.age + 'd'}}</td>
    </tr>`).join('');

  if (list.length > 400) {{
    $('rows').insertAdjacentHTML('beforeend',
      `<tr><td colspan="7" style="color:var(--muted)">Showing first 400 of
       ${{list.length.toLocaleString()}} — narrow the filters to see the rest.</td></tr>`);
  }}
}}

['q','family','seniority'].forEach(id =>
  $(id).addEventListener('input', render));

['dataOnly','remoteOnly','payOnly'].forEach(id =>
  $(id).addEventListener('click', e => {{
    const on = e.currentTarget.getAttribute('aria-pressed') === 'true';
    e.currentTarget.setAttribute('aria-pressed', String(!on));
    render();
  }}));

document.querySelectorAll('th[data-sort]').forEach(th =>
  th.addEventListener('click', () => {{
    const key = th.dataset.sort;
    state.dir = state.sort === key ? -state.dir : 1;
    state.sort = key;
    render();
  }}));

render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(build())
