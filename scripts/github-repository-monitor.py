#!/usr/bin/env python3
"""Daily GitHub activity digest for all public repositories owned by Narsing-s.

Requires GH_MONITOR_TOKEN (repo/traffic read access) and SMTP_* secrets.
GitHub does not expose identities for repository views or clones; those are aggregate metrics.
"""
import json, os, smtplib, urllib.request, urllib.error
from datetime import datetime, timezone
from email.message import EmailMessage

OWNER = "Narsing-s"
TOKEN = os.environ["GH_MONITOR_TOKEN"]
API = "https://api.github.com"
headers = {"Accept":"application/vnd.github+json", "Authorization":f"Bearer {TOKEN}", "X-GitHub-Api-Version":"2022-11-28", "User-Agent":"Narsing-s-repository-monitor"}

def get(path):
    req = urllib.request.Request(API + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (403, 404): return None
        raise

def main():
    repos = get(f"/users/{OWNER}/repos?per_page=100&type=owner&sort=updated") or []
    repos = [r for r in repos if r.get("owner",{}).get("login","").lower()==OWNER.lower()]
    rows, activity = [], []
    for repo in repos:
        name = repo["full_name"]
        traffic = get(f"/repos/{name}/traffic/views") or {}
        clones = get(f"/repos/{name}/traffic/clones") or {}
        views = traffic.get("views", [])
        clone_days = clones.get("clones", [])
        view_total = sum(x.get("count",0) for x in views)
        unique_total = sum(x.get("uniques",0) for x in views)
        clone_total = sum(x.get("count",0) for x in clone_days)
        clone_unique = sum(x.get("uniques",0) for x in clone_days)
        rows.append((name, view_total, unique_total, clone_total, clone_unique))
        events = get(f"/repos/{name}/events?per_page=100") or []
        for ev in events:
            typ = ev.get("type")
            if typ not in ("WatchEvent","ForkEvent","IssuesEvent","PullRequestEvent","IssueCommentEvent","PullRequestReviewEvent","PullRequestReviewCommentEvent","ReleaseEvent"):
                continue
            actor = (ev.get("actor") or {}).get("login","unknown")
            payload = ev.get("payload") or {}
            action = payload.get("action","")
            if typ == "WatchEvent": label = "starred"
            elif typ == "ForkEvent": label = "forked"
            elif typ == "IssuesEvent": label = f"issue {action}"
            elif typ == "PullRequestEvent": label = f"pull request {action}"
            elif typ == "ReleaseEvent": label = "published a release"
            elif typ == "IssueCommentEvent": label = "commented on an issue"
            elif typ == "PullRequestReviewEvent": label = "reviewed a pull request"
            else: label = "commented on a pull request review"
            subject = (payload.get("issue") or payload.get("pull_request") or payload.get("release") or {}).get("title","")
            activity.append(f"- **{name}**: @{actor} {label}" + (f" — {subject}" if subject else "") + f" ([event]({ev.get('html_url','https://github.com/'+name)}))")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_views=sum(x[1] for x in rows); total_uniques=sum(x[2] for x in rows)
    total_clones=sum(x[3] for x in rows); total_clone_uniques=sum(x[4] for x in rows)
    lines = [f"# GitHub repository activity — {stamp}", "", f"Repositories monitored: **{len(repos)}**", "",
             "| Repository | Views (14d) | Unique visitors* | Clones (14d) | Unique cloners* |",
             "|---|---:|---:|---:|---:|"]
    for name,v,u,c,cu in rows:
        lines.append(f"| [{name}](https://github.com/{name}) | {v} | {u} | {c} | {cu} |")
    lines += ["", f"**Totals:** {total_views} views · {total_uniques} unique visitors · {total_clones} clones · {total_clone_uniques} unique cloners", "",
              "## Recent public activity", ""]
    lines += activity[:150] if activity else ["No matching public events found in the latest event pages."]
    lines += ["", "*GitHub reports aggregate traffic only; it does not reveal who viewed or cloned a repository. Traffic endpoints may be unavailable without repository admin-level access. Event feed is public and may be delayed or incomplete.*"]
    body="\n".join(lines)
    print(body)
    msg=EmailMessage()
    msg["Subject"]=f"[GitHub Monitor] {len(repos)} repositories — {stamp}"
    msg["From"]=os.environ["SMTP_FROM"]
    msg["To"]=os.environ.get("REPORT_TO", os.environ["SMTP_FROM"])
    msg.set_content(body)
    host=os.environ.get("SMTP_HOST","smtp.gmail.com")
    port=int(os.environ.get("SMTP_PORT","465"))
    with smtplib.SMTP_SSL(host,port,timeout=30) as server:
        server.login(os.environ["SMTP_USERNAME"],os.environ["SMTP_PASSWORD"])
        server.send_message(msg)

if __name__=="__main__": main()
