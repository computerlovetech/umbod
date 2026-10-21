from datetime import datetime

from ..models import OAuthConnectorDefinition
from ..personal_oauth_configuration import PersonalOAuthPolicy
from .authorization_models import ExpiringPersonalToken, PersonalOAuthGrant
from .models import Authorized, PersonalConnectionKey


def validated_bound_grant(
    authorization: Authorized,
    key: PersonalConnectionKey,
    now: datetime,
    definition: OAuthConnectorDefinition,
    policy: PersonalOAuthPolicy,
) -> PersonalOAuthGrant:
    grant = PersonalOAuthGrant.model_validate_json(authorization.authorization.get_secret_value())
    client = policy.client
    method = client.token_endpoint_auth_method if client.kind == "preconfigured_confidential" else "none"
    if (
        grant.key != key
        or grant.resource != definition.endpoint_url
        or grant.configuration_revision != policy.revision
        or grant.requested_scopes != policy.requested_scopes
        or grant.client_mode != client.kind
        or grant.token_endpoint_auth_method != method
        or (client.kind != "dynamic_public" and (grant.issuer != client.issuer_url or grant.client_id != client.client_id))
        or grant.issued_at > now
        or not isinstance(grant.lifetime, ExpiringPersonalToken)
    ):
        raise ValueError("Unsupported personal authorization")
    return grant
