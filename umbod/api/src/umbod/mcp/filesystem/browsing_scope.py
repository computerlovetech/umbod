from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.browsing.exploration import NodeTarget, PathTarget, Target
from umbod.core.filesystem.homes import HomeService


class PersonalNamespaceTargets:
    def __init__(self, browsing: FilesystemBrowsing, homes: HomeService) -> None:
        self._browsing = browsing
        self._homes = homes

    async def resolve(self, caller: CallerSnapshot, target: Target) -> NodeTarget:
        if isinstance(target, NodeTarget):
            return target
        node = await self._homes.get_or_provision(caller)
        if isinstance(target, PathTarget):
            for segment in filter(None, target.path.split("/")):
                children = await self._browsing.list_children(caller, node.id)
                matches = [child for child in children if child.name == segment]
                if len(matches) != 1:
                    raise PermissionDenied()
                node = matches[0]
        return NodeTarget(type="node", node_id=node.id)
