from .manifest import PROTOCOL_VERSION,SEMVER
JAMESOS_VERSION="0.1.0"
def _parts(value):return tuple(int(item) for item in value.split("-")[0].split("+")[0].split("."))
def compatibility(manifest,jamesos_version=JAMESOS_VERSION):
    if manifest.protocol_version.split(".")[0]!=PROTOCOL_VERSION.split(".")[0]:return "incompatible_protocol"
    if _parts(jamesos_version)<_parts(manifest.minimum_jamesos_version):return "jamesos_too_old"
    if manifest.maximum_jamesos_version and _parts(jamesos_version)>_parts(manifest.maximum_jamesos_version):return "jamesos_too_new"
    return "compatible"

