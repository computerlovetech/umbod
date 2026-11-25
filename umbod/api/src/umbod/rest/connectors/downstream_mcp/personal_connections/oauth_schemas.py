from pydantic import BaseModel, ConfigDict

from umbod.core.connectors.downstream_mcp.personal.oauth.authorization import PersonalOAuthAttemptView


class PersonalOAuthStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PersonalOAuthAttemptResponse(PersonalOAuthAttemptView):
    pass


class PersonalOAuthStartResponse(PersonalOAuthAttemptResponse):
    authorization_url: str
