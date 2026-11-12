import hashlib
import json

from umbod.core.callers import (
    LOCAL_DEVELOPMENT_ISSUER,
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)

from .models import UnavailableUsageOwner, UsageOwner, UsageOwnership


def resolve_usage_owner(caller: CallerContext) -> UsageOwnership:
    subject = caller.subject
    if not isinstance(subject, SubjectIdentity) or not isinstance(subject.issuer, DeclaredIssuer):
        return UnavailableUsageOwner(kind='unavailable')
    issuer = subject.issuer.value
    if not issuer.strip() or not subject.subject.strip():
        return UnavailableUsageOwner(kind='unavailable')
    trusted = caller.authentication == AuthenticationProvenance.UPSTREAM_VERIFIED
    local = (
        caller.authentication == AuthenticationProvenance.LOCAL_SIMULATION
        and issuer == LOCAL_DEVELOPMENT_ISSUER
    )
    if not trusted and not local:
        return UnavailableUsageOwner(kind='unavailable')
    encoded = json.dumps([issuer, subject.subject], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return UsageOwner(kind='owned', owner_id=hashlib.sha256(b'umbod.usage.owner.v1\x00' + encoded).hexdigest())
