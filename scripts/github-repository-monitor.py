#!/usr/bin/env python3
"""HTML + text GitHub activity digest for repositories owned by Narsing-s."""
import html
import json
import os
import smtplib
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.message import EmailMessage

OWNER = "Narsing-s"
TOKEN = os.environ["GH_MONITOR_TOKEN"]
API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "Narsing-s-repository-monitor",
}
WARNINGS = []

def get(path):
    req = urllib.request.Request(API + path, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as exc:
        detail = f"HTTP {exc.code}"
        if exc.code in (403, 404):
            WARNINGS.append(f"{path}: {detail} — unavailable or insufficient token permission")
            return None
        body = exc.read().decode(errors="replace")[:300]
        WARNINGS.append(f"{path}: {detail} {body}")
        return None
    except Exception as exc:
        WARNINGS.append(f"{path}: {type(exc).__name__}: {exc}")
        return None

def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)

def event_description(ev):
    typ = ev.get("type", "")
    p = ev.get("payload") or {}
    action = p.get("action", "")
    issue = p.get("issue") or p.get("pull_request") or {}
    pr = p.get("pull_request") or {}
    release = p.get("release") or {}
    repo = ev.get("repo", {}).get("name", "")
    actor = (ev.get("actor") or {}).get("login", "unknown")
    subject = issue.get("title") or release.get("name") or ""
    url = issue.get("html_url") or release.get("html_url") or ("https://github.com/" + repo)
    if typ == "WatchEvent":
        detail = "starred this repository"
    elif typ == "ForkEvent":
        detail = "forked this repository"
        if p.get("forkee", {}).get("full_name"):
            subject = "Fork: " + p["forkee"]["full_name"]
    elif typ == "IssuesEvent":
        detail = f"{action or 'updated'} an issue"
    elif typ == "PullRequestEvent":
        detail = f"{action or 'updated'} a pull request"
        subject = pr.get("title") or subject
        url = pr.get("html_url") or url
    elif typ == "IssueCommentEvent":
        detail = "commented on an issue"
        subject = (p.get("comment") or {}).get("body", "")[:180] or subject
    elif typ == "PullRequestReviewEvent":
        review = p.get("review") or {}
        detail = "reviewed a pull request"
        subject = review.get("state", "") + (": " + subject if subject else "")
    elif typ == "PullRequestReviewCommentEvent":
        detail = "commented on a pull request review"
        subject = (p.get("comment") or {}).get("body", "")[:180] or subject
    elif typ == "ReleaseEvent":
        detail = f"{action or 'published'} a release"
    elif typ == "PushEvent":
        commits = p.get("commits") or []
        detail = f"pushed {p.get('size', len(commits))} commit(s) to {p.get('ref', 'a branch')}"
        subject = " · ".join(c.get("message", "").splitlines()[0] for c in commits[:3] if c.get("message"))
    elif typ == "CreateEvent":
        detail = f"created {p.get('ref_type', 'a ref')} {p.get('ref') or ''}".strip()
    elif typ == "DeleteEvent":
        detail = f"deleted {p.get('ref_type', 'a ref')} {p.get('ref') or ''}".strip()
    elif typ == "PublicEvent":
        detail = "made this repository public"
    elif typ == "GollumEvent":
        detail = "updated repository wiki pages"
        subject = ", ".join(x.get("page_name", "") for x in p.get("pages", [])[:4])
    elif typ == "CommitCommentEvent":
        detail = "commented on a commit"
        subject = (p.get("comment") or {}).get("body", "")[:180]
    else:
        detail = typ.replace("Event", " event") or "activity"
    return {
        "actor": actor, "repo": repo, "detail": detail,
        "subject": subject, "url": url, "created": ev.get("created_at", ""),
        "type": typ,
    }

def fetch_repositories():
    result = []
    for page in range(1, 11):
        batch = get(f"/users/{OWNER}/repos?per_page=100&type=owner&sort=updated&page={page}") or []
        if not batch:
            break
        result.extend(r for r in batch if r.get("owner", {}).get("login", "").lower() == OWNER.lower())
        if len(batch) < 100:
            break
    return result

def traffic_for(repo):
    name = repo["full_name"]
    views = get(f"/repos/{name}/traffic/views")
    clones = get(f"/repos/{name}/traffic/clones")
    referrers = get(f"/repos/{name}/traffic/popular/referrers")
    paths = get(f"/repos/{name}/traffic/popular/paths")
    view_days = (views or {}).get("views", [])
    clone_days = (clones or {}).get("clones", [])
    return {
        "name": name,
        "url": repo.get("html_url", "https://github.com/" + name),
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "open_issues": repo.get("open_issues_count", 0),
        "views": sum(x.get("count", 0) for x in view_days),
        "daily_unique": sum(x.get("uniques", 0) for x in view_days),
        "clones": sum(x.get("count", 0) for x in clone_days),
        "daily_clone_unique": sum(x.get("uniques", 0) for x in clone_days),
        "view_days": view_days,
        "clone_days": clone_days,
        "referrers": referrers or [],
        "paths": paths or [],
        "traffic_available": views is not None or clones is not None,
    }

def main():
    repos = fetch_repositories()
    reports = []
    activities = []
    for repo in repos:
        reports.append(traffic_for(repo))
        events = get(f"/repos/{repo['full_name']}/events?per_page=100") or []
        for ev in events:
            item = event_description(ev)
            if item["type"] in {
                "WatchEvent", "ForkEvent", "IssuesEvent", "PullRequestEvent",
                "IssueCommentEvent", "PullRequestReviewEvent",
                "PullRequestReviewCommentEvent", "ReleaseEvent", "PushEvent",
                "CreateEvent", "DeleteEvent", "PublicEvent", "GollumEvent",
                "CommitCommentEvent",
            }:
                activities.append(item)

    activities.sort(key=lambda x: x["created"], reverse=True)
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    totals = {
        key: sum(r[key] for r in reports)
        for key in ("views", "daily_unique", "clones", "daily_clone_unique", "stars", "forks")
    }
    available = sum(1 for r in reports if r["traffic_available"])

    # Plain-text alternative
    text_lines = [
        f"GITHUB REPOSITORY INTELLIGENCE — {stamp}",
        f"Owner: {OWNER} | Repositories: {len(repos)}",
        "",
        "PROFILE VIEWS: Not available — GitHub does not expose profile-page view analytics via its API.",
        "",
        f"TOTALS: {totals['views']} repository views; {totals['daily_unique']} summed daily unique views; "
        f"{totals['clones']} clones; {totals['daily_clone_unique']} summed daily unique cloners; "
        f"{totals['stars']} stars; {totals['forks']} forks.",
        f"Traffic API returned data for {available}/{len(reports)} repositories.",
        "",
        "REPOSITORY TRAFFIC (last 14 days)",
    ]
    for r in reports:
        text_lines.append(
            f"{r['name']}: {r['views']} views, {r['daily_unique']} summed daily uniques, "
            f"{r['clones']} clones, {r['stars']} stars, {r['forks']} forks"
        )
        if r["view_days"]:
            text_lines.append("  Daily views: " + ", ".join(
                f"{x.get('timestamp','')[:10]} {x.get('count',0)} views/{x.get('uniques',0)} daily uniques"
                for x in r["view_days"]
            ))
        if r["referrers"]:
            text_lines.append("  Referrers: " + ", ".join(
                f"{x.get('referrer','unknown')} ({x.get('count',0)})" for x in r["referrers"][:5]
            ))
        if r["paths"]:
            text_lines.append("  Popular paths: " + ", ".join(
                f"{x.get('path','')} ({x.get('count',0)})" for x in r["paths"][:5]
            ))
    text_lines += ["", "RECENT PUBLIC ACTIVITY"]
    for a in activities[:200]:
        text_lines.append(f"{a['created']} — @{a['actor']} {a['detail']} in {a['repo']}: {a['subject']} ({a['url']})")
    if WARNINGS:
        text_lines += ["", "DATA WARNINGS"] + [f"- {w}" for w in WARNINGS[:30]]
    text_lines += [
        "",
        "Note: daily unique counts are summed across days and are not a deduplicated 14-day person count. "
        "GitHub does not identify people who only view or clone repositories. Public event feeds are incomplete/delayed.",
    ]
    plain = "\n".join(text_lines)

    # HTML email — clear sections, responsive tables, readable on mobile.
    css = """
    body{margin:0;background:#f4f6fa;color:#172033;font-family:Arial,Helvetica,sans-serif}
    .wrap{max-width:900px;margin:0 auto;padding:22px 12px}
    .hero{background:#172033;color:#fff;padding:24px;border-radius:14px}
    .hero h1{font-size:22px;margin:0 0 8px}.muted{color:#aab6ca;font-size:13px}
    .grid{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}
    .metric{background:#fff;border:1px solid #e4e8f0;border-radius:10px;padding:14px;flex:1;min-width:125px}
    .metric b{display:block;font-size:24px;margin-top:5px}.metric span{font-size:12px;color:#657189}
    .section{background:#fff;border:1px solid #e4e8f0;border-radius:12px;padding:16px;margin:14px 0}
    h2{font-size:17px;margin:0 0 12px}h3{font-size:14px;margin:16px 0 8px}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th{text-align:left;background:#f1f4f9;color:#536078}
    th,td{padding:9px 8px;border-bottom:1px solid #e8ecf2;vertical-align:top}
    a{color:#1769d2;text-decoration:none}.pill{display:inline-block;background:#eef3ff;color:#315aa8;padding:4px 8px;border-radius:20px;font-size:11px}
    .activity{padding:10px 0;border-bottom:1px solid #edf0f5;font-size:13px;line-height:1.5}
    .activity:last-child{border:0}.small{font-size:12px;color:#68758b}
    .notice{background:#fff8e8;border:1px solid #f0dfb5;padding:12px;border-radius:9px;font-size:13px;line-height:1.5}
    .scroll{overflow-wrap:anywhere}
    @media(max-width:600px){.wrap{padding:10px 7px}.hero{padding:18px}.metric{min-width:40%}th,td{padding:7px 5px;font-size:12px}}
    """
    parts = [f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{css}</style></head><body><div class="wrap">
    <div class="hero"><h1>GitHub Repository Intelligence</h1><div class="muted">{esc(OWNER)} · {esc(stamp)}</div><p>Traffic, discovery sources and public activity across {len(repos)} owned repositories.</p></div>
    <div class="grid">
    <div class="metric"><span>Repository views · 14 days</span><b>{totals['views']:,}</b></div>
    <div class="metric"><span>Daily unique views summed*</span><b>{totals['daily_unique']:,}</b></div>
    <div class="metric"><span>Clones · 14 days</span><b>{totals['clones']:,}</b></div>
    <div class="metric"><span>Stars · current total</span><b>{totals['stars']:,}</b></div>
    <div class="metric"><span>Forks · current total</span><b>{totals['forks']:,}</b></div>
    </div>
    <div class="notice"><b>Profile views:</b> GitHub does not provide profile-page view counts through its official API. Repository traffic is available for {available} of {len(reports)} repositories. A missing traffic result is not the same as zero views.</div>
    <div class="section"><h2>Repository overview</h2><div class="scroll"><table><thead><tr><th>Repository</th><th>Views</th><th>Daily uniques*</th><th>Clones</th><th>Stars</th><th>Forks</th></tr></thead><tbody>"""]
    for r in sorted(reports, key=lambda x: x["views"], reverse=True):
        parts.append(
            f"<tr><td><a href='{esc(r['url'])}'>{esc(r['name'].split('/',1)[-1])}</a>"
            f"{'' if r['traffic_available'] else '<br><span class=small>Traffic unavailable</span>'}</td>"
            f"<td>{r['views']:,}</td><td>{r['daily_unique']:,}</td><td>{r['clones']:,}</td>"
            f"<td>{r['stars']:,}</td><td>{r['forks']:,}</td></tr>"
        )
    parts.append("</tbody></table></div></div>")

    for r in sorted(reports, key=lambda x: x["views"], reverse=True):
        parts.append(f"<div class='section'><h2><a href='{esc(r['url'])}'>{esc(r['name'])}</a></h2>")
        parts.append(f"<p><span class='pill'>{r['views']:,} views</span> <span class='pill'>{r['clones']:,} clones</span> <span class='pill'>{r['stars']:,} stars</span></p>")
        parts.append("<h3>Daily traffic · last 14 days</h3>")
        if r["view_days"]:
            parts.append("<table><thead><tr><th>Date</th><th>Views</th><th>Unique views*</th></tr></thead><tbody>")
            for d in r["view_days"]:
                parts.append(f"<tr><td>{esc(d.get('timestamp','')[:10])}</td><td>{d.get('count',0):,}</td><td>{d.get('uniques',0):,}</td></tr>")
            parts.append("</tbody></table>")
        else:
            parts.append("<p class='small'>No view breakdown returned by GitHub for this repository.</p>")
        if r["clone_days"]:
            parts.append("<h3>Daily clones</h3><table><thead><tr><th>Date</th><th>Clones</th><th>Unique cloners*</th></tr></thead><tbody>")
            for d in r["clone_days"]:
                parts.append(f"<tr><td>{esc(d.get('timestamp','')[:10])}</td><td>{d.get('count',0):,}</td><td>{d.get('uniques',0):,}</td></tr>")
            parts.append("</tbody></table>")
        if r["referrers"]:
            parts.append("<h3>Where visitors came from</h3><table><tr><th>Referrer</th><th>Views</th><th>Uniques*</th></tr>")
            for x in r["referrers"][:10]:
                parts.append(f"<tr><td>{esc(x.get('referrer',''))}</td><td>{x.get('count',0):,}</td><td>{x.get('uniques',0):,}</td></tr>")
            parts.append("</table>")
        if r["paths"]:
            parts.append("<h3>Most viewed repository pages</h3><table><tr><th>Path</th><th>Views</th><th>Uniques*</th></tr>")
            for x in r["paths"][:10]:
                parts.append(f"<tr><td class='scroll'>{esc(x.get('path',''))}</td><td>{x.get('count',0):,}</td><td>{x.get('uniques',0):,}</td></tr>")
            parts.append("</table>")
        parts.append("</div>")

    parts.append("<div class='section'><h2>Recent public activity</h2>")
    if activities:
        for a in activities[:200]:
            subject = f" — {esc(a['subject'])}" if a["subject"] else ""
            parts.append(
                f"<div class='activity'><b>@{esc(a['actor'])}</b> {esc(a['detail'])} "
                f"in <a href='https://github.com/{esc(a['repo'])}'>{esc(a['repo'])}</a>{subject}"
                f"<br><span class='small'>{esc(a['created'])} · <a href='{esc(a['url'])}'>Open event</a></span></div>"
            )
    else:
        parts.append("<p class='small'>No matching public events were returned in the recent event feed.</p>")
    parts.append("</div>")
    if WARNINGS:
        parts.append("<div class='section'><h2>Data access warnings</h2><ul>")
        for warning in WARNINGS[:30]:
            parts.append(f"<li class='small'>{esc(warning)}</li>")
        parts.append("</ul></div>")
    parts.append("""<p class="small">*Daily unique values are summed across days; they are not a deduplicated 14-day count of individual people. GitHub does not reveal identities of people who only view or clone repositories. Public events may be delayed or incomplete. Traffic is limited to GitHub's recent 14-day window.</p></div></body></html>""")
    html_body = "".join(parts)

    msg = EmailMessage()
    msg["Subject"] = f"[GitHub Monitor] {len(repos)} repositories · {stamp}"
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = os.environ.get("REPORT_TO", os.environ["SMTP_FROM"])
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")
    print(plain)
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"),
                          int(os.environ.get("SMTP_PORT", "465")), timeout=30) as server:
        server.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        server.send_message(msg)

if __name__ == "__main__":
    main()
