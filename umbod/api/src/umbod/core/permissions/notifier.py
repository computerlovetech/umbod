class NoopPermissionChangeNotifier:
    def permissions_changed(self) -> bool:
        return False
