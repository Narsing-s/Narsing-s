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
PROFILE_HEADLINE = os.environ.get(
    "PROFILE_HEADLINE",
    "Building reliable integrations, production systems and open-source tools."
)
# Manually supplied snapshot; GitHub's official API does not expose profile views.
PROFILE_VIEWS_SNAPSHOT = os.environ.get("PROFILE_VIEWS_SNAPSHOT", "389")
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
    issue = p.get("issue") or {}
    pr = p.get("pull_request") or {}
    comment = p.get("comment") or {}
    review = p.get("review") or {}
    release = p.get("release") or {}
    repo = ev.get("repo", {}).get("name", "")
    actor = (ev.get("actor") or {}).get("login", "unknown")
    subject = issue.get("title") or pr.get("title") or release.get("name") or ""
    number = issue.get("number") or pr.get("number")
    url = (pr.get("html_url") or issue.get("html_url") or
           comment.get("html_url") or review.get("html_url") or
           release.get("html_url") or "")
    if typ == "WatchEvent":
        detail = "starred the repository"
    elif typ == "ForkEvent":
        detail = "forked the repository"
        subject = (p.get("forkee") or {}).get("full_name") or subject
        url = (p.get("forkee") or {}).get("html_url") or url
    elif typ == "IssuesEvent":
        detail = f"{action or 'updated'} issue"
    elif typ == "PullRequestEvent":
        detail = f"{action or 'updated'} pull request"
    elif typ == "IssueCommentEvent":
        detail = "commented on an issue"
        subject = issue.get("title") or subject
        url = comment.get("html_url") or issue.get("html_url") or url
    elif typ == "PullRequestReviewEvent":
        detail = f"submitted a {review.get('state', 'new').lower()} review"
        subject = pr.get("title") or subject
        url = review.get("html_url") or pr.get("html_url") or url
    elif typ == "PullRequestReviewCommentEvent":
        detail = "commented on a pull request"
        subject = pr.get("title") or subject
        url = comment.get("html_url") or pr.get("html_url") or url
    elif typ == "ReleaseEvent":
        detail = f"{action or 'published'} a release"
    elif typ == "PushEvent":
        commits = p.get("commits") or []
        detail = f"pushed {p.get('size', len(commits))} commit(s) to {p.get('ref', 'a branch')}"
        subject = " · ".join(c.get("message", "").splitlines()[0] for c in commits[:2] if c.get("message"))
        if commits:
            url = f"https://github.com/{repo}/commit/{commits[0].get('sha','')}"
    elif typ == "CreateEvent":
        detail = f"created {p.get('ref_type', 'a ref')} {p.get('ref') or ''}".strip()
    elif typ == "DeleteEvent":
        detail = f"deleted {p.get('ref_type', 'a ref')} {p.get('ref') or ''}".strip()
    elif typ == "PublicEvent":
        detail = "made the repository public"
    elif typ == "GollumEvent":
        detail = "updated repository wiki"
        subject = ", ".join(x.get("page_name", "") for x in p.get("pages", [])[:3])
    elif typ == "CommitCommentEvent":
        detail = "commented on a commit"
        subject = comment.get("body", "")[:140]
        url = comment.get("html_url") or url
    else:
        detail = typ.replace("Event", " event") or "activity"
    if number and not subject:
        subject = f"#{number}"
    if number and url and f"/{number}" not in url:
        url = f"https://github.com/{repo}/{'pull' if typ == 'PullRequestEvent' or pr else 'issues'}/{number}"
    return {
        "id": str(ev.get("id", "")), "actor": actor, "repo": repo,
        "detail": detail, "subject": subject, "number": number,
        "url": url or f"https://github.com/{repo}", "created": ev.get("created_at", ""),
        "type": typ, "is_bot": actor.endswith("[bot]"),
        "is_owner": actor.lower() == OWNER.lower(),
    }

def group_bot_activity(items):
    grouped = {}
    for item in items:
        key = (item["actor"], item["repo"], item["detail"], item["subject"])
        if key not in grouped:
            grouped[key] = dict(item, count=0)
        grouped[key]["count"] += 1
        if item["created"] > grouped[key]["created"]:
            grouped[key]["created"] = item["created"]
    return sorted(grouped.values(), key=lambda x: x["created"], reverse=True)

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

    # De-duplicate events, then separate people, owner activity and automation.
    unique = {}
    for item in activities:
        unique[item["id"] or f"{item['actor']}|{item['repo']}|{item['type']}|{item['created']}"] = item
    activities = list(unique.values())
    people_activity = [x for x in activities if not x["is_bot"] and not x["is_owner"]]
    owner_activity = [x for x in activities if x["is_owner"]]
    bot_activity = group_bot_activity([x for x in activities if x["is_bot"]])
    for group in (people_activity, owner_activity):
        group.sort(key=lambda x: x["created"], reverse=True)
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
        f"PROFILE: {PROFILE_HEADLINE}",
        f"PROFILE VIEWS: {PROFILE_VIEWS_SNAPSHOT} (manual snapshot supplied 21 Nov 2026; not live API data).",
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
    def plain_activity(title, items):
        text_lines.extend(["", title, "=" * len(title)])
        headers = ["DATE / TIME (UTC)", "USERNAME", "ACTION", "REPOSITORY", "ITEM / TITLE", "COUNT", "DIRECT LINK"]
        rows = []
        for a in items[:80]:
            rows.append([
                a.get("created", "").replace("T", " ")[:19],
                "@" + a.get("actor", "unknown"),
                a.get("detail", ""),
                a.get("repo", ""),
                a.get("subject", ""),
                str(a.get("count", 1)) if a.get("count", 1) > 1 else "",
                a.get("url", ""),
            ])
        widths = [min(max(len(headers[i]), *(len(row[i]) for row in rows)) if rows else len(headers[i]), 34)
                  for i in range(len(headers))]
        def cell(value, width):
            value = str(value).replace("\\n", " ").replace("\\r", " ")
            return value if len(value) <= width else value[:width-1] + "…"
        def table_line(row):
            return "| " + " | ".join(cell(row[i], widths[i]).ljust(widths[i]) for i in range(len(headers))) + " |"
        text_lines.append(table_line(headers))
        text_lines.append("|-" + "-|-".join("-" * w for w in widths) + "-|")
        if not rows:
            text_lines.append("| " + "No matching activity found.".ljust(sum(widths) + 3 * (len(widths)-1)) + " |")
        else:
            text_lines.extend(table_line(row) for row in rows)
    plain_activity("ACTIVITY BY OTHER PEOPLE", people_activity)
    plain_activity("YOUR ACTIVITY", owner_activity)
    plain_activity("AUTOMATION / BOT ACTIVITY (GROUPED)", bot_activity)
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
    <div class="section"><h2>GitHub profile</h2><p><b>Headline:</b> {esc(PROFILE_HEADLINE)}</p><p><b>Profile views:</b> {esc(PROFILE_VIEWS_SNAPSHOT)} <span class="small">(manual snapshot supplied 21 Nov 2026; not a live API count)</span></p><p class="small">GitHub's official API does not expose profile-page view analytics. Update PROFILE_VIEWS_SNAPSHOT when you have a newer count.</p></div>
    <div class="notice"><b>Repository traffic:</b> available for {available} of {len(reports)} repositories. A missing traffic result is not the same as zero views.</div>
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

    def add_activity_section(title, items, bot_group=False):
        parts.append(f"<div class='section'><h2>{esc(title)} <span class='pill'>{len(items)}</span></h2>")
        parts.append("<div class='scroll'><table><thead><tr><th>Date / time (UTC)</th><th>Username</th><th>Action</th><th>Repository</th><th>Item / title</th><th>Count</th><th>Link</th></tr></thead><tbody>")
        if not items:
            parts.append("<tr><td colspan='7' class='small'>No matching activity found in the recent public event feed.</td></tr>")
        for a in items[:80]:
            subject = esc(a.get("subject") or (f"#{a['number']}" if a.get("number") else "—"))
            count = a.get("count", 1)
            count_text = str(count) if count > 1 else "1"
            link_label = "Open item" if a.get("number") or a.get("subject") else "Open repository"
            parts.append(
                f"<tr><td>{esc(a.get('created','').replace('T',' ')[:19])}</td>"
                f"<td><b>@{esc(a.get('actor','unknown'))}</b></td>"
                f"<td>{esc(a.get('detail',''))}</td>"
                f"<td><a href='https://github.com/{esc(a.get('repo',''))}'>{esc(a.get('repo',''))}</a></td>"
                f"<td>{subject}</td><td>{count_text}</td>"
                f"<td><a href='{esc(a.get('url',''))}'>{link_label}</a></td></tr>"
            )
        parts.append("</tbody></table></div></div>")
    add_activity_section("Activity by other people", people_activity)
    add_activity_section("Your activity", owner_activity)
    add_activity_section("Automation and bot activity (repetitions grouped)", bot_activity, True)
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
