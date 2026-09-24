from umbod.core.invocation.policy import ConnectorInvocationPolicyRecord
from messaging.models import MessagingEvent


def connector_invocation_policy_changed_event(
    record: ConnectorInvocationPolicyRecord,
) -> MessagingEvent:
    key = record.key
    return MessagingEvent(
        event_type="connector.invocation_policy.changed",
        subject=f"connector:{key.connector_kind}:{key.connector_id}:tool:{key.operation_name}:invocation-policy",
        metadata={
            "connector_kind": key.connector_kind,
            "connector_id": key.connector_id,
            "operation_name": key.operation_name,
            "mode": record.mode,
            "revision": str(record.revision),
        },
    )


__all__ = ["connector_invocation_policy_changed_event"]
