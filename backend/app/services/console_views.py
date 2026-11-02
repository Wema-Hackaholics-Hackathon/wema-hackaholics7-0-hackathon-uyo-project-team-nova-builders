"""Read models for the business console: Users table and Overview numbers.

A "user" in the console is a Subject — anyone this business verified in this
environment, whether or not they have a FOID account. Status per person:

  revoked   they withdrew consent (no active grant left)
  verified  latest verification passed, or (no hosted verification) a direct check passed
  declined  latest verification failed / expired / was cancelled, or only failed checks
  pending   started and not finished (includes needs_review)

Personal data follows consent exactly like the API: name only with the
`identity` scope, email only with `contact`. Search only looks at what the
business can see.

Computed in Python from four queries per org+env. Fine for the current scale;
move to a denormalised status column if an org grows past ~50k subjects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import CheckResult, ConsentGrant, Subject, Verification
from app.services.checks_service import as_utc, iso, utcnow

STATUSES = ("verified", "pending", "declined", "revoked")
_CHECK_LABEL = {"nin": "NIN", "bvn": "BVN", "liveness": "Liveness", "reverify": "Re-verify", "address": "Address"}


def subject_code(subject_id: str) -> str:
    """Short, stable code shown in the console: FOID-1A2B-3C4D (first 8 hex chars of the id)."""
    hexed = subject_id.replace("-", "")[:8].upper()
    return f"FOID-{hexed[:4]}-{hexed[4:]}"


@dataclass
class Row:
    subject: Subject
    scopes: set[str] = field(default_factory=set)
    had_grant: bool = False
    latest: Verification | None = None
    checks: dict[str, str] = field(default_factory=dict)        # type → latest status
    passed_at: datetime | None = None

    @property
    def status(self) -> str:
        if self.had_grant and not self.scopes:
            return "revoked"
        v = self.latest
        if v is not None:
            if v.outcome == "passed":
                return "verified"
            if v.outcome == "failed" or v.status in ("cancelled", "expired"):
                return "declined"
            return "pending"
        if self.checks:
            return "verified" if "passed" in self.checks.values() else "declined"
        return "pending"

    @property
    def verified_at(self) -> datetime | None:
        if self.status != "verified":
            return None
        return (self.latest.completed_at if self.latest and self.latest.completed_at else None) or self.passed_at

    def out(self) -> dict[str, Any]:
        s = self.subject
        identity, contact = "identity" in self.scopes, "contact" in self.scopes
        name = " ".join(p for p in (s.first_name, s.last_name) if p) if identity else None
        return {
            "id": s.id,
            "code": subject_code(s.id),
            "customer_ref": s.customer_ref,
            "name": name or None,
            "email": s.email if contact else None,
            "checks": [_CHECK_LABEL.get(t, t) for t in sorted(self.checks)],
            "status": self.status,
            "has_foid_account": s.user_id is not None,
            "verified_at": iso(self.verified_at),
            "created_at": iso(s.created_at),
        }

    def matches(self, q: str) -> bool:
        q = q.strip().lower()
        if not q:
            return True
        o = self.out()
        hexq = q.replace("foid", "").replace("-", "")
        return (
            (len(hexq) >= 4 and self.subject.id.replace("-", "").startswith(hexq))
            or any(q in (v or "").lower() for v in (o["name"], o["email"], o["customer_ref"]))
        )


async def rows(db: AsyncSession, org_id: str, env: str) -> list[Row]:
    subjects = (await db.exec(select(Subject).where(Subject.org_id == org_id, Subject.env == env)
                              .order_by(Subject.created_at.desc()))).all()  # pyright: ignore[reportAttributeAccessIssue]
    by_id = {s.id: Row(s) for s in subjects}
    if not by_id:
        return []
    for g in (await db.exec(select(ConsentGrant).where(ConsentGrant.org_id == org_id))).all():
        r = by_id.get(g.subject_id)
        if r:
            r.had_grant = True
            if g.status == "active":
                r.scopes.update(g.scopes)
    for v in (await db.exec(select(Verification).where(Verification.org_id == org_id, Verification.env == env)
                            .order_by(Verification.created_at))).all():  # pyright: ignore[reportArgumentType]
        if r := by_id.get(v.subject_id):
            r.latest = v                                              # ordered → last one wins
    for c in (await db.exec(select(CheckResult).where(CheckResult.org_id == org_id, CheckResult.env == env)
                            .order_by(CheckResult.created_at))).all():  # pyright: ignore[reportArgumentType]
        if r := by_id.get(c.subject_id):
            r.checks[c.type] = c.status
            if c.status == "passed":
                r.passed_at = c.created_at
    return list(by_id.values())


def counts(all_rows: list[Row]) -> dict[str, int]:
    out = {s: 0 for s in STATUSES}
    for r in all_rows:
        out[r.status] += 1
    return {"all": len(all_rows), **out}


async def overview(db: AsyncSession, org_id: str, env: str) -> dict[str, Any]:
    """Numbers for the Overview page: people, verification rate/time, funnel, trend."""
    now = utcnow()
    month, prev = now - timedelta(days=30), now - timedelta(days=60)
    all_rows = await rows(db, org_id, env)
    vs = (await db.exec(select(Verification).where(Verification.org_id == org_id, Verification.env == env))).all()
    recent = [v for v in vs if (as_utc(v.created_at) or now) >= month]
    previous = [v for v in vs if prev <= (as_utc(v.created_at) or now) < month]
    passed = [v for v in recent if v.outcome == "passed" and v.completed_at]
    completed = [v for v in recent if v.status == "completed"]

    durations = [((as_utc(v.completed_at) or now) - (as_utc(v.created_at) or now)).total_seconds() for v in passed]
    passed_check_ids = {c.verification_id for c in (await db.exec(select(CheckResult).where(
        CheckResult.org_id == org_id, CheckResult.env == env, CheckResult.status == "passed"))).all() if c.verification_id}
    stuck_before = now - timedelta(minutes=30)
    stuck = [v for v in recent if v.status in ("pending", "in_progress") and (as_utc(v.created_at) or now) < stuck_before]

    return {
        "env": env,
        "users": counts(all_rows),
        "verifications_30d": len(recent),
        "verifications_prev_30d": len(previous),
        "pass_rate": round(len(passed) / len(completed), 3) if completed else None,
        "avg_verification_seconds": round(sum(durations) / len(durations)) if durations else None,
        "funnel": {
            "started": len(recent),
            "identity_confirmed": sum(1 for v in recent if v.id in passed_check_ids),
            "fully_verified": len(passed),
        },
        "stuck": len(stuck),
        "foid_account_share": round(sum(1 for r in all_rows if r.subject.user_id) / len(all_rows), 3) if all_rows else None,
    }

