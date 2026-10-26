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


class ProvisioningConflict(Exception):
    pass


class StorageFailure(Exception):
    pass
