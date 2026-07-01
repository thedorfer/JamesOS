from mcp.server.fastmcp import FastMCP
from jamesos.tools import notes

mcp = FastMCP("JamesOS")

mcp.tool()(notes.list_notes)
mcp.tool()(notes.read_note)
mcp.tool()(notes.write_note)
mcp.tool()(notes.append_note)
mcp.tool()(notes.search_notes)
mcp.tool()(notes.create_daily_note)
mcp.tool()(notes.create_ticket)
mcp.tool()(notes.create_meeting_note)
mcp.tool()(notes.move_note)

if __name__ == "__main__":
    mcp.run()
