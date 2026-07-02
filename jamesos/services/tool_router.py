import ast
import operator
from datetime import datetime
from zoneinfo import ZoneInfo

from jamesos.config.loader import get_config


OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def detect_tool(question: str) -> str:
    q = question.lower()

    if any(w in q for w in ["weather", "temperature", "forecast", "rain", "snow"]):
        return "weather"

    if any(w in q for w in ["search the web", "look up", "research online", "latest", "news"]):
        return "web_search"

    if any(w in q for w in ["calculate", "what is", "+", "-", "*", "/", "%"]):
        if any(ch.isdigit() for ch in q):
            return "calculator"

    if any(w in q for w in ["time in", "current time", "what time"]):
        return "time"

    return "local"


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value

    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))

    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_safe_eval(node.operand))

    raise ValueError("Unsupported calculation")


def calculator_tool(expression: str) -> str:
    tree = ast.parse(expression, mode="eval")
    return str(_safe_eval(tree.body))


def time_tool(timezone: str = "America/Chicago") -> str:
    now = datetime.now(ZoneInfo(timezone))
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


def weather_tool(question: str) -> str:
    cfg = get_config("tools.yaml").get("tools", {}).get("weather", {})
    if not cfg.get("enabled", False):
        return "Weather tool is not configured yet."

    return "Weather tool provider is pending."


def web_search_tool(question: str) -> str:
    cfg = get_config("tools.yaml").get("tools", {}).get("web_search", {})
    if not cfg.get("enabled", False):
        return "Web search tool is not configured yet."

    return "Web search provider is pending."


def route_tool(question: str) -> dict:
    tool = detect_tool(question)

    try:
        if tool == "calculator":
            expr = question.lower().replace("calculate", "").replace("what is", "").strip(" ?")
            result = calculator_tool(expr)
        elif tool == "time":
            result = time_tool()
        elif tool == "weather":
            result = weather_tool(question)
        elif tool == "web_search":
            result = web_search_tool(question)
        else:
            result = "No external tool selected."
    except Exception as exc:
        result = f"Tool failed: {exc}"

    return {
        "tool": tool,
        "result": result,
    }
