from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.users.profiles import UserProfile, UserProfileInput


def _string_claim(claims: JwtClaims, key: str, neutral: str) -> str:
    value = claims.claims.get(key)
    return value if isinstance(value, str) and value.strip() else neutral


class ClaimProfileMapper:
    def __init__(self, name_claim: str, email_claim: str, picture_claim: str) -> None:
        self.name_claim = name_claim
        self.email_claim = email_claim
        self.picture_claim = picture_claim

    def map(self, claims: JwtClaims) -> UserProfile:
        return UserProfile(
            name=_string_claim(claims, self.name_claim, "unknown"),
            email=_string_claim(claims, self.email_claim, ""),
            picture=_string_claim(claims, self.picture_claim, ""),
        )


class AccessClaimsUserProfileProvider:
    def __init__(self, mapper: ClaimProfileMapper) -> None:
        self.mapper = mapper

    def get_profile(self, profile_input: UserProfileInput) -> UserProfile:
        return self.mapper.map(profile_input.access_claims)
