from mcp.server.fastmcp import FastMCP
from jamesos.tools import notes
from jamesos.tools import work
from jamesos.tools import inbox
from jamesos.services.dashboard import generate_home_dashboard
from jamesos.services.work_dashboard import generate_work_dashboard
from jamesos.services.refresh import refresh_dashboards
from jamesos.services.day import start_day
from jamesos.services.eod import end_day
from jamesos.services.indexer import build_entity_index
from jamesos.services.relationship_engine import build_internal_db, build_relationship_index

def build_server() -> FastMCP:
    mcp = FastMCP("JamesOS")

    mcp.tool()(notes.list_notes)
    mcp.tool()(notes.read_note)
    mcp.tool()(notes.write_note)
    mcp.tool()(notes.append_note)
    mcp.tool()(notes.search_notes)
    mcp.tool()(notes.create_daily_note)
    mcp.tool()(notes.create_ticket)
    mcp.tool()(work.create_work_ticket)
    mcp.tool()(work.update_work_ticket_status)
    mcp.tool()(work.append_work_ticket_log)
    mcp.tool()(inbox.capture_inbox)
    mcp.tool()(notes.create_meeting_note)
    mcp.tool()(notes.move_note)
    mcp.tool()(generate_home_dashboard)
    mcp.tool()(generate_work_dashboard)
    mcp.tool()(refresh_dashboards)
    mcp.tool()(start_day)
    mcp.tool()(end_day)
    mcp.tool()(build_entity_index)
    mcp.tool()(build_relationship_index)
    mcp.tool()(build_internal_db)

    return mcp

def main() -> None:
    mcp = build_server()
    mcp.run()
