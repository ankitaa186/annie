#!/usr/bin/env python3
"""
Story 23.1 (AC7) — Cost Reconciliation Tool

Pulls `type=GENERATION` observations from Langfuse for a date range and
produces a per-day markdown table comparing Annie's recorded cost to a
manually-entered "Google billed" column. The operator fills the billed
column from the Google Cloud Console billing detail.

This script does NOT integrate with Google Cloud Billing API — that's a
separate followup story (Epic 23 future work). For now it stops at giving
the operator a side-by-side view they can paste billing numbers into.

Usage:
    # Print to stdout
    python scripts/cost_reconciliation.py --start 2026-04-01 --end 2026-04-25

    # Write to a markdown file
    python scripts/cost_reconciliation.py --start 2026-03-26 --end 2026-04-25 \\
        --output reports/cost_2026-03-26_to_2026-04-25.md

    # Filter by release tag (default: annie-prod)
    python scripts/cost_reconciliation.py --start 2026-04-01 --end 2026-04-25 \\
        --release annie-dev

    # Smoke test without hitting Langfuse (uses synthetic data)
    python scripts/cost_reconciliation.py --dry-run

    # Filter by model substring (default: gemini)
    python scripts/cost_reconciliation.py --start 2026-04-01 --end 2026-04-25 \\
        --model-filter gemini

Environment:
    LANGFUSE_PUBLIC_KEY  — required (unless --dry-run)
    LANGFUSE_SECRET_KEY  — required (unless --dry-run)
    LANGFUSE_HOST        — defaults to https://us.cloud.langfuse.com

Story 23.1 (AC8) follow-up reconciliation calendar:
    See TODO block below — manual reconciliation reminders at
    2026-05-02 (+7d), 2026-05-09 (+14d), 2026-05-25 (+30d).
"""

# TODO(Story 23.1, AC8 — manual reconciliation calendar)
# After 23.1 merges, run this script and paste Google Cloud Console
# billing detail into the "google_billed" column on these dates:
#
#   2026-05-02  (+7  days post-merge) — informational; expect <88% gap
#   2026-05-09  (+14 days post-merge) — informational; gap should be narrower
#   2026-05-25  (+30 days post-merge) — TARGET: variance <10%
#
# If +30d variance is still above 25%, open Story 23.2 to dig into
# remaining gap sources (untraced SDK retries, count_tokens billing on
# residual call sites, etc.). Disha owns posting calendar reminders.

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)


DEFAULT_LANGFUSE_HOST = "https://us.cloud.langfuse.com"
DEFAULT_RELEASE = "annie-prod"
DEFAULT_MODEL_FILTER = "gemini"
PAGE_SIZE = 100


@dataclass
class DayBucket:
    """Aggregated stats for one calendar day (UTC)."""
    date: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    recorded_cost: float = 0.0
    missing_usage_count: int = 0
    error_count: int = 0
    models: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile Annie's recorded LLM cost (Langfuse) vs Google's billed cost.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--start", help="Start date YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (inclusive)")
    parser.add_argument(
        "--release",
        default=DEFAULT_RELEASE,
        help=f"Filter by release tag (default: {DEFAULT_RELEASE})",
    )
    parser.add_argument(
        "--model-filter",
        default=DEFAULT_MODEL_FILTER,
        help=(
            f"Substring to match against the model name (default: '{DEFAULT_MODEL_FILTER}'). "
            "Pass empty string to include all models."
        ),
    )
    parser.add_argument(
        "--output",
        help="Path to write markdown output. Defaults to stdout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use synthetic data instead of hitting Langfuse (smoke test).",
    )
    return parser.parse_args()


def fetch_observations(
    host: str,
    public_key: str,
    secret_key: str,
    start_iso: str,
    end_iso: str,
) -> List[dict]:
    """Page through GET /api/public/observations with type=GENERATION."""
    url = f"{host.rstrip('/')}/api/public/observations"
    page = 1
    out: List[dict] = []

    with httpx.Client(timeout=30.0, auth=(public_key, secret_key)) as client:
        while True:
            params = {
                "type": "GENERATION",
                "fromStartTime": start_iso,
                "toStartTime": end_iso,
                "limit": PAGE_SIZE,
                "page": page,
            }
            resp = client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", []) or []
            out.extend(data)
            meta = payload.get("meta") or {}
            total_pages = meta.get("totalPages") or 0
            if not data or page >= total_pages:
                break
            page += 1
    return out


def synthetic_observations() -> List[dict]:
    """Two days of fake data to smoke-test aggregation/rendering."""
    today = datetime.now(timezone.utc).replace(microsecond=0)
    yesterday = today - timedelta(days=1)
    return [
        {
            "startTime": today.isoformat().replace("+00:00", "Z"),
            "model": "gemini-3.1-pro-preview",
            "release": DEFAULT_RELEASE,
            "usage": {"input": 1234, "output": 567, "total": 1801},
            "calculatedTotalCost": 0.012,
            "level": "DEFAULT",
        },
        {
            "startTime": today.isoformat().replace("+00:00", "Z"),
            "model": "gemini-3.1-pro-preview",
            "release": DEFAULT_RELEASE,
            "usage": {},  # missing-usage scenario
            "calculatedTotalCost": 0,
            "level": "ERROR",
            "statusMessage": "RateLimitError: quota exceeded",
        },
        {
            "startTime": yesterday.isoformat().replace("+00:00", "Z"),
            "model": "gemini-3-pro-preview",
            "release": DEFAULT_RELEASE,
            "usage": {"input": 2000, "output": 800, "total": 2800},
            "calculatedTotalCost": 0.0212,
            "level": "DEFAULT",
        },
    ]


def aggregate(
    observations: List[dict],
    release: Optional[str],
    model_filter: str,
) -> Dict[str, DayBucket]:
    buckets: Dict[str, DayBucket] = {}
    for obs in observations:
        # Optional release filter (Langfuse REST currently lacks server-side
        # release filtering on /observations, so we filter client-side).
        if release:
            obs_release = obs.get("release") or (obs.get("metadata") or {}).get("release")
            if obs_release and obs_release != release:
                continue

        model = obs.get("model") or "<unknown>"
        if model_filter and model_filter.lower() not in model.lower():
            continue

        start = obs.get("startTime") or obs.get("createdAt")
        if not start:
            continue
        try:
            # Langfuse uses ISO-8601 with trailing Z. Normalize.
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            continue
        date_key = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")

        bucket = buckets.setdefault(date_key, DayBucket(date=date_key))
        bucket.calls += 1
        bucket.models[model] += 1

        usage = obs.get("usage") or {}
        # Langfuse v2 ModelUsage: input / output (or promptTokens / completionTokens)
        input_tokens = usage.get("input") or usage.get("promptTokens") or 0
        output_tokens = usage.get("output") or usage.get("completionTokens") or 0
        if not input_tokens and not output_tokens:
            bucket.missing_usage_count += 1
        bucket.input_tokens += int(input_tokens or 0)
        bucket.output_tokens += int(output_tokens or 0)

        cost = obs.get("calculatedTotalCost") or obs.get("totalCost") or 0
        try:
            bucket.recorded_cost += float(cost or 0)
        except (TypeError, ValueError):
            pass

        if (obs.get("level") or "").upper() == "ERROR":
            bucket.error_count += 1
    return buckets


def render_markdown(
    buckets: Dict[str, DayBucket],
    start: str,
    end: str,
    release: str,
    model_filter: str,
) -> str:
    lines: List[str] = []
    lines.append(f"# Cost Reconciliation: {start} to {end}")
    lines.append("")
    lines.append(
        f"_Filter: release=`{release}`, model contains `{model_filter or '*'}`. "
        f"Source: Annie's Langfuse-recorded cost. Fill `google_billed` from "
        f"Google Cloud Console billing detail._"
    )
    lines.append("")
    lines.append(
        "| date | calls | input_tokens | output_tokens | recorded_cost | google_billed |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|"
    )
    total_calls = 0
    total_input = 0
    total_output = 0
    total_cost = 0.0
    for date_key in sorted(buckets.keys()):
        b = buckets[date_key]
        total_calls += b.calls
        total_input += b.input_tokens
        total_output += b.output_tokens
        total_cost += b.recorded_cost
        lines.append(
            f"| {b.date} | {b.calls} | {b.input_tokens:,} | {b.output_tokens:,} | "
            f"${b.recorded_cost:,.4f} | _(fill in)_ |"
        )
    lines.append(
        f"| **TOTAL** | **{total_calls}** | **{total_input:,}** | **{total_output:,}** | "
        f"**${total_cost:,.4f}** | **_(fill in)_** |"
    )
    lines.append("")

    # Diagnostics section helps spot the same patterns Parminder flagged.
    missing = sum(b.missing_usage_count for b in buckets.values())
    errors = sum(b.error_count for b in buckets.values())
    lines.append("## Diagnostics")
    lines.append("")
    lines.append(f"- Generations missing usage data: **{missing}** "
                 f"(post-23.1 these should be <1% of total calls; AC10 watchdog)")
    lines.append(f"- Generations with `level=ERROR`: **{errors}** "
                 f"(AC5 — these are the cap-trip / 429 traces we now record)")
    if buckets:
        zero_days = [b.date for b in buckets.values() if b.calls == 0]
        if zero_days:
            lines.append(f"- Zero-call days: {', '.join(zero_days)}")
    lines.append("")
    lines.append("## Notes for the operator")
    lines.append("")
    lines.append(
        "1. Open Google Cloud Console → Billing → Reports, filter by Generative "
        "Language API, set the same date range. Paste daily $ totals into the "
        "`google_billed` column."
    )
    lines.append(
        "2. Compute variance = `(recorded - billed) / billed`. The 23.1 target "
        "is <10% variance at +30 days post-merge."
    )
    lines.append(
        "3. If variance stays >25% at +30d, open Story 23.2 to investigate "
        "untraced SDK-internal retries and any residual `count_tokens` billing."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()

    if args.dry_run:
        observations = synthetic_observations()
        # In dry-run we don't have a meaningful date range — derive from data.
        dates = [o["startTime"][:10] for o in observations if o.get("startTime")]
        start = args.start or (min(dates) if dates else datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        end = args.end or (max(dates) if dates else datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    else:
        if not args.start or not args.end:
            print("ERROR: --start and --end are required (or use --dry-run).", file=sys.stderr)
            return 2
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY") or ""
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY") or ""
        host = os.environ.get("LANGFUSE_HOST") or DEFAULT_LANGFUSE_HOST
        if not public_key or not secret_key:
            print(
                "ERROR: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set "
                "(or pass --dry-run for a smoke test).",
                file=sys.stderr,
            )
            return 2
        # ISO 8601 boundaries (UTC). Inclusive on both ends.
        start_iso = f"{args.start}T00:00:00.000Z"
        end_iso = f"{args.end}T23:59:59.999Z"
        try:
            observations = fetch_observations(host, public_key, secret_key, start_iso, end_iso)
        except httpx.HTTPError as e:
            print(f"ERROR: Langfuse REST call failed: {e}", file=sys.stderr)
            return 1
        start, end = args.start, args.end

    buckets = aggregate(observations, release=args.release, model_filter=args.model_filter)
    md = render_markdown(buckets, start, end, args.release, args.model_filter)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as fh:
            fh.write(md)
        print(f"Wrote: {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
