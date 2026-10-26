from .models import FaviconDiscoveryRequest, FaviconFound, FaviconNotFound


class AdvertisedIconStrategy:
    async def discover(
        self, request: FaviconDiscoveryRequest
    ) -> FaviconFound | FaviconNotFound:
        if request.advertised_icons:
            return FaviconFound(icon=request.advertised_icons[0], strategy="advertised")
        return FaviconNotFound()
