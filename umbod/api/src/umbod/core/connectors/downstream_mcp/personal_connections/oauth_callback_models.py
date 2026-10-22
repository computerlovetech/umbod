import hashlib
import re
from typing import Annotated, Literal
from urllib.parse import unquote

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from ..personal_oauth_configuration.models import validate_configured_issuer


def validate_callback_uri(value: str) -> str:
    if not value.startswith("http://"):
        return validate_configured_issuer(value)
    decoded = unquote(value)
    if any(ord(character) <= 32 or ord(character) >= 127 for character in value + decoded) or "\\" in decoded:
        raise ValueError("Invalid callback URI")
    match = re.fullmatch(r"http://(localhost|127\.0\.0\.1|\[::1\])(?::([1-9][0-9]{0,4}))?(/[^?#\\]*)?", value)
    if match is None or (match[2] and int(match[2]) > 65535):
        raise ValueError("Invalid callback URI")
    return value


class CallbackModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MissingCallbackIssuer(CallbackModel):
    kind: Literal["missing"]


class PresentCallbackIssuer(CallbackModel):
    kind: Literal["present"]
    value: str = Field(min_length=1)


CallbackIssuer = Annotated[MissingCallbackIssuer | PresentCallbackIssuer, Field(discriminator="kind")]


class GenericRoute(CallbackModel):
    kind: Literal["generic"]


class IssuerRoute(CallbackModel):
    kind: Literal["issuer"]
    issuer_key: str = Field(pattern=r"^[a-f0-9]{64}$")


CallbackRoute = Annotated[GenericRoute | IssuerRoute, Field(discriminator="kind")]


class LegacyGenericBinding(CallbackModel):
    kind: Literal["legacy_generic"]


class GenericBinding(CallbackModel):
    kind: Literal["generic"]
    expected_issuer: str = Field(min_length=1)


class IssuerBinding(CallbackModel):
    kind: Literal["issuer"]
    expected_issuer: str = Field(min_length=1)
    redirect_uri: str = Field(min_length=1)
    issuer_key: str = Field(pattern=r"^[a-f0-9]{64}$")


CallbackBinding = Annotated[
    LegacyGenericBinding | GenericBinding | IssuerBinding, Field(discriminator="kind")
]


def issuer_route_key(issuer: str) -> str:
    validate_configured_issuer(issuer)
    return hashlib.sha256(issuer.encode("utf-8")).hexdigest()


def issuer_callback_uri(base_uri: str, issuer: str) -> str:
    validate_callback_uri(base_uri)
    return base_uri + "/issuer/" + issuer_route_key(issuer)


def validate_callback_binding(
    binding: CallbackBinding, base_uri: str, route: CallbackRoute, issuer: CallbackIssuer,
) -> str:
    if isinstance(binding, IssuerBinding):
        expected_redirect = issuer_callback_uri(base_uri, binding.expected_issuer)
        if (
            not isinstance(route, IssuerRoute)
            or route.issuer_key != binding.issuer_key
            or binding.issuer_key != issuer_route_key(binding.expected_issuer)
            or binding.redirect_uri != expected_redirect
            or (isinstance(issuer, PresentCallbackIssuer) and issuer.value != binding.expected_issuer)
        ):
            raise ValueError("Invalid callback binding")
        return expected_redirect
    if not isinstance(route, GenericRoute) or not isinstance(issuer, PresentCallbackIssuer) or not issuer.value:
        raise ValueError("Invalid generic callback binding")
    if isinstance(binding, GenericBinding) and issuer.value != binding.expected_issuer:
        raise ValueError("Invalid callback issuer")
    return base_uri


OAuthCallbackURI = Annotated[
    str, Field(min_length=1, max_length=4096), AfterValidator(validate_callback_uri)
]
