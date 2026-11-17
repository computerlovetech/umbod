from importlib.metadata import distribution
from importlib.resources import files

from umbod.core.harness_plugins.ports import InstallerSource, PackageResources, ScriptKind


class BundledInstallerSourceReader:
    def read(self, kind: ScriptKind) -> InstallerSource:
        if kind not in {"sh", "ps1"}:
            raise ValueError("Unsupported installer source")
        resource = files("umbod.rest.install").joinpath("assets", "install." + kind)
        with resource.open("rb") as stream:
            content = stream.read(262145)
        if len(content) > 262144:
            raise ValueError("Installer source exceeds the resource limit")
        return InstallerSource(text=content.decode("utf-8"))


class BundledPackageResourceReader:
    def read(self) -> PackageResources:
        resources = distribution("umbod-core").locate_file("umbod/harness_plugin_resources")
        with resources.joinpath("SKILL.md").open("rb") as stream:
            skill = stream.read(262145).decode("utf-8")
        with resources.joinpath("AGENT_BEHAVIOUR_SKILL.md").open("rb") as stream:
            behaviour_skill = stream.read(262145).decode("utf-8")
        with resources.joinpath("LICENSE").open("rb") as stream:
            license_text = stream.read(262145).decode("utf-8")
        return PackageResources(skill=skill, behaviour_skill=behaviour_skill, license_text=license_text)
