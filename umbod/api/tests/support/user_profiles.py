from umbod.rest.users.profiles import UserProfile, UserProfileInput


class InMemoryUserProfileProvider:
    def __init__(self, profile: UserProfile) -> None:
        self.profile = profile

    def get_profile(self, profile_input: UserProfileInput) -> UserProfile:
        return self.profile
