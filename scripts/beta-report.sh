#!/bin/bash
# Beta usage report — calls GET /api/admin/beta-report and renders markdown.
#
# Usage:
#   ./scripts/beta-report.sh            # qa, last 14 days, top 10 users
#   ./scripts/beta-report.sh prod 30 20 # prod, last 30 days, top 20 users
#   ./scripts/beta-report.sh qa 14 10 > reports/beta-$(date +%Y%m%d).md
#
# Requires: aws-cli (to fetch ADMIN_API_KEY from secretsmanager), curl, python3, jq.
# Reads from snugd/{env}/secrets in us-east-1.

set -euo pipefail

ENV="${1:-qa}"
DAYS="${2:-14}"
TOP_N="${3:-10}"

case "$ENV" in
  qa)   BASE_URL="https://api-qa.snugd.ai" ;;
  prod) BASE_URL="https://api.snugd.ai" ;;
  dev)  BASE_URL="https://api-dev.snugd.ai" ;;
  *)    echo "Unknown env: $ENV (expected qa|prod|dev)" >&2; exit 1 ;;
esac

ADMIN_KEY=$(aws secretsmanager get-secret-value \
  --secret-id "snugd/${ENV}/secrets" \
  --region us-east-1 \
  --query SecretString --output text | jq -r .ADMIN_API_KEY)

if [ -z "$ADMIN_KEY" ] || [ "$ADMIN_KEY" = "null" ]; then
  echo "Could not fetch ADMIN_API_KEY for $ENV from secretsmanager" >&2
  exit 1
fi

JSON=$(curl -sS -fL --max-time 30 \
  -H "X-Admin-Key: $ADMIN_KEY" \
  "${BASE_URL}/api/admin/beta-report?days=${DAYS}&top_n=${TOP_N}")

# Pipe through Python for markdown formatting. Inlined here (vs a separate
# .py file) so the script is one self-contained deliverable.
echo "$JSON" | python3 - "$ENV" "$DAYS" <<'PYEOF'
import json, sys
from datetime import datetime

env = sys.argv[1]
days = sys.argv[2]
data = json.load(sys.stdin)

def fmt_dt(s):
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return s

print(f"# Beta Usage Report — {env.upper()} — generated {fmt_dt(data['generated_at'])}")
print(f"\n_Engagement window: last {days} days._\n")

# ─── Invite codes ──────────────────────────────────────────────────
print("## Invite codes\n")
codes = data.get("invite_codes") or []
if not codes:
    print("_(no codes minted)_\n")
else:
    print("| Code | Used | Max | Remaining | Last redeemed | Expires |")
    print("|---|---:|---:|---:|---|---|")
    for c in codes:
        # Surface times_used vs actual_redemptions divergence — usually
        # they match; if not, that's an atomic-counter bug worth chasing.
        used_str = str(c["times_used"])
        if c["times_used"] != c["actual_redemptions"]:
            used_str = f"{c['times_used']} (actual {c['actual_redemptions']})"
        print(f"| `{c['code']}` | {used_str} | {c['max_uses']} | {c['remaining']} | {fmt_dt(c['last_redeemed_at'])} | {fmt_dt(c['expires_at'])} |")
    print()

# ─── Cohort ────────────────────────────────────────────────────────
co = data.get("cohort") or {}
print("## Beta cohort (users who redeemed any code)\n")
print(f"- **Total redeemers:** {co.get('total_redeemers', 0)}")
print(f"- Pro (active): {co.get('pro_active', 0)}")
print(f"- Pro (expired): {co.get('pro_expired', 0)}")
print(f"- Free: {co.get('free', 0)}")
if co.get("unknown"):
    print(f"- Profile not found: {co['unknown']}")
print()

# ─── Tours ─────────────────────────────────────────────────────────
t = data.get("tours") or {}
print("## Tour pipeline\n")
print(f"- **Total tours:** {t.get('total', 0)}")
print(f"- Created in last {days} days: {t.get('in_lookback_window', 0)}")
by_stage = t.get("by_stage") or {}
if by_stage:
    print("\n**By stage:** " + ", ".join(f"{k}: {v}" for k, v in sorted(by_stage.items(), key=lambda kv: -kv[1])))
by_decision = t.get("by_decision") or {}
if by_decision:
    print("\n**Decisions:** " + ", ".join(f"{k}: {v}" for k, v in by_decision.items()))
print()

# ─── Engagement aggregates ─────────────────────────────────────────
print("## Engagement aggregates\n")
print(f"- Saved searches: **{data.get('saved_searches_total', 0)}**")
print(f"- Tour notes: **{data.get('tour_notes_total', 0)}**")
print(f"- Tour photos: **{data.get('tour_photos_total', 0)}**")
ev = data.get("analytics_events") or {}
print(f"- Analytics events in window: **{ev.get('total_in_window', 0)}** "
      f"({', '.join(f'{k}={v}' for k, v in (ev.get('by_type_in_window') or {}).items()) or '—'})")
print()

# ─── Top users ─────────────────────────────────────────────────────
top = data.get("top_users") or []
print(f"## Top {len(top)} most-active beta users\n")
if not top:
    print("_(no engagement yet)_\n")
else:
    print("| User | Tours | Notes | Photos | Saved | Score | Last active |")
    print("|---|---:|---:|---:|---:|---:|---|")
    for u in top:
        label = u.get("email") or u.get("name") or (u.get("user_id") or "—")[:8] + "…"
        tier = u.get("tier") or "?"
        print(f"| {label} _(t:{tier})_ | {u['tours']} | {u['notes']} | {u['photos']} | {u['saved_searches']} | **{u['activity_score']}** | {fmt_dt(u.get('last_active'))} |")
    print()

# ─── Feedback ──────────────────────────────────────────────────────
fb = data.get("feedback") or {}
print("## Beta feedback\n")
print(f"- **Total submissions:** {fb.get('total', 0)}")
by_type = fb.get("by_type") or {}
if by_type:
    print("- By type: " + ", ".join(f"{k}={v}" for k, v in by_type.items()))
recent = fb.get("recent") or []
if recent:
    print("\n**Most recent:**\n")
    for r in recent:
        msg = (r.get("message") or "").replace("\n", " ")
        print(f"- `{r.get('type', '?')}` ({fmt_dt(r.get('created_at'))}): {msg}")
print()
PYEOF
