from pydantic import ConfigDict

from umbod.proxies import Model
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization import PersonalOAuthAttemptView


class PersonalOAuthStartRequest(Model):
    model_config = ConfigDict(extra="forbid", strict=True)


class PersonalOAuthAttemptResponse(PersonalOAuthAttemptView):
    pass


class PersonalOAuthStartResponse(PersonalOAuthAttemptResponse):
    authorization_url: str
