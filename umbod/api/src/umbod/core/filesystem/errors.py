class OwnershipNotFound(Exception):
    pass


class MissingNode(Exception):
    pass


class NameCollision(Exception):
    pass


class InvalidName(Exception):
    pass


class WrongNodeKind(Exception):
    pass


class RevisionConflict(Exception):
    pass


class InvalidMove(Exception):
    pass


class RootMutation(Exception):
    pass


class StorageFailure(Exception):
    pass


class PolicyDecodingFailure(StorageFailure):
    pass


class PolicyRevisionConflict(Exception):
    pass


class PolicyConflict(Exception):
    pass


class PolicyUnavailable(Exception):
    pass
