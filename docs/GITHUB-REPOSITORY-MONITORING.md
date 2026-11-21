# GitHub repository monitoring

The monitor runs from the `Narsing-s/Narsing-s` profile repository and checks repositories owned by `Narsing-s`.

## Email report

The report is sent as a responsive HTML email with a plain-text fallback. It includes:

- A portfolio overview with repository views, summed daily unique views, clones, current stars and current forks.
- Per-repository daily view and clone breakdowns for the recent 14-day window.
- Popular referrers and popular repository paths when GitHub returns them.
- Recent public activity with actor, repository, event/action, available title or detail, timestamp, and link.
- Data-access warnings where GitHub denies or does not return traffic data.

The daily unique values are summed across dates. They are not a deduplicated count of distinct people over the full 14 days.

## Profile views and visitor identities

GitHub's official REST API does not expose profile-page view analytics. The report therefore labels profile views as unavailable rather than inventing a number. If profile README page-load counting is desired, a separate counter/analytics integration can be added, but it would count loads of that embedded README asset and would not identify every visitor to the GitHub profile page.

GitHub traffic endpoints provide aggregate repository views and clones. They do not reveal the usernames of people who only viewed or cloned a repository. Identities are shown only for public activities where GitHub exposes an actor, such as stars, forks, issue/PR activity, comments, reviews, pushes, releases, and selected repository events. The public event feed is not a complete audit log and may be delayed.

## Access and limits

- Repository traffic is available only for repositories the token can access with sufficient permissions. A missing/denied traffic response is displayed as unavailable, not treated as a confirmed zero.
- GitHub's traffic API returns a rolling recent 14-day window.
- The workflow enumerates up to 1,000 owned repositories (10 pages × 100).
- Recent activity uses each repository's public event feed (up to 100 events per repository).

## Required GitHub Actions secrets

Open **Narsing-s/Narsing-s → Settings → Secrets and variables → Actions** and configure:

| Secret | Value |
|---|---|
| `GH_MONITOR_TOKEN` | Fine-grained PAT with access to all owned repositories; Repository permissions: **Metadata: Read** and **Administration: Read**. |
| `SMTP_HOST` | `smtp.gmail.com` for Gmail, or your provider's SMTP host. |
| `SMTP_PORT` | `465` for SSL SMTP. |
| `SMTP_USERNAME` | Email account used to send the report. |
| `SMTP_PASSWORD` | SMTP/app password. For Gmail, use an App Password after enabling 2-Step Verification. |
| `SMTP_FROM` | Sender email address, usually the same as SMTP_USERNAME. |
| `REPORT_TO` | Destination email address for the digest. |

Never commit tokens or mail passwords into repository files.

## Run and schedule

- Workflow: **Actions → GitHub Repository Monitor → Run workflow** for a manual report.
- Schedule: daily at 09:00 India time.
- Workflow file: `.github/workflows/repository-monitor.yml`.

If a repository shows unavailable traffic, inspect the Actions log for the corresponding API warning and check the token's repository access and permissions.
