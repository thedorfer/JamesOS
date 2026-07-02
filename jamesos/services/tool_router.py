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
    import json
    import re
    import urllib.parse
    import urllib.request

    cfg = get_config("tools.yaml").get("tools", {}).get("weather", {})
    if not cfg.get("enabled", False):
        return "Weather tool is not configured yet."

    q = question.lower()

    # Simple city extraction for v1.
    location = "Chicago"
    match = re.search(r"in ([a-zA-Z .'-]+?)(?: on | tomorrow| today|$)", question)
    if match:
        location = match.group(1).strip()

    geo_url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        + urllib.parse.urlencode({"name": location, "count": 1, "language": "en", "format": "json"})
    )

    with urllib.request.urlopen(geo_url, timeout=15) as resp:
        geo = json.loads(resp.read().decode("utf-8"))

    results = geo.get("results", [])
    if not results:
        return f"Could not find weather location: {location}"

    place = results[0]
    lat = place["latitude"]
    lon = place["longitude"]
    name = place.get("name", location)
    admin = place.get("admin1", "")
    country = place.get("country", "")

    forecast_url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
            "forecast_days": 7,
        })
    )

    with urllib.request.urlopen(forecast_url, timeout=15) as resp:
        forecast = json.loads(resp.read().decode("utf-8"))

    daily = forecast.get("daily", {})
    times = daily.get("time", [])
    highs = daily.get("temperature_2m_max", [])
    lows = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_probability_max", [])

    lines = [f"Weather for {name}, {admin}, {country}".replace(" ,", ""), ""]

    for i, day in enumerate(times[:7]):
        lines.append(
            f"- {day}: high {highs[i]}°F, low {lows[i]}°F, precip chance {precip[i]}%"
        )

    return "\n".join(lines)

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
