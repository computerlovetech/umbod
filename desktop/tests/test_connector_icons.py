from pathlib import Path
import unittest


DESKTOP = Path(__file__).resolve().parents[1]


class ConnectorIconWiringTests(unittest.TestCase):
    def test_inventory_icon_reaches_swift_connector_row(self):
        client = (DESKTOP / "native/Sources/UmbodCore/AdministrationClient.swift").read_text()
        view = (DESKTOP / "native/Sources/Umbod/ConnectorsView.swift").read_text()

        self.assertIn('server["icon_url"] = iconURL', client)
        self.assertIn('ConnectorIconView(', view)
        self.assertIn('server["icon_url"] as? String', view)


if __name__ == "__main__":
    unittest.main()
