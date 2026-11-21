# GitHub repository monitoring setup

This monitor lives in the `Narsing-s/Narsing-s` profile repository and checks repositories owned by `Narsing-s`.

## What it reports

- Daily aggregate repository views and unique visitors (last 14 days, as returned by GitHub).
- Daily aggregate clones and unique cloners (last 14 days).
- Recent public stars, forks, issues, pull requests, comments, reviews, and releases from GitHub's public event feed.
- One email digest per successful scheduled run.

GitHub does not expose the identity of people who merely view or clone a repository. Traffic totals are aggregate counts. Traffic API access can require repository administrator-level access; inaccessible repositories are shown with zero counts in this first version, so check the workflow log and permissions before treating zero as a true zero.

## Required GitHub Actions secrets

Open **Narsing-s/Narsing-s → Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|---|---|
| `GH_MONITOR_TOKEN` | Fine-grained PAT for the account, with access to all owned repositories; Repository permissions: **Metadata: Read** and **Administration: Read** (needed for traffic endpoints). |
| `SMTP_HOST` | `smtp.gmail.com` for Gmail, or your provider's SMTP host. |
| `SMTP_PORT` | `465` for SSL SMTP. |
| `SMTP_USERNAME` | Email account used to send the report. |
| `SMTP_PASSWORD` | SMTP/app password (for Gmail, create an App Password after enabling 2-Step Verification). Never use your normal account password. |
| `SMTP_FROM` | Sender email address, usually the same as SMTP_USERNAME. |
| `REPORT_TO` | Destination email address for the digest. |

Do not commit tokens or mail passwords into repository files.

## Run and notifications

- Workflow: **Actions → GitHub Repository Monitor → Run workflow** for an initial manual test.
- It also runs daily at 09:00 India time.
- To receive GitHub-side workflow notifications, open the profile repository's **Watch → Custom**, enable **Actions**, and ensure GitHub notification delivery is enabled in your account notification settings.
- The email digest is sent only after the required secrets are configured and the workflow succeeds.

## Limitations

GitHub traffic is aggregate and limited to the recent 14-day window. Public event feeds can be delayed/incomplete and do not provide a complete audit log. This workflow monitors all repositories returned by GitHub's owner repository listing (first 100); the current account listing contains 60.
