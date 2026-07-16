from jamesos.core.agent_manager.manifest import CAPABILITY
def capability(value):
    if not CAPABILITY.fullmatch(value):raise ValueError("invalid JamesOS capability")
    return value

