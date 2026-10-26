from umbod.core.filesystem.administration import RootGroupPolicyView


class RootAccessResponse(RootGroupPolicyView):
    suggested_issuer: str
    group_claim: str
