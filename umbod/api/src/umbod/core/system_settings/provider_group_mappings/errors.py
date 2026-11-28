class UnregisteredMappingGroups(ValueError):
    def __init__(self, indexes: tuple[int, ...]) -> None:
        super().__init__("Mapping target groups are not registered")
        self.indexes = indexes
