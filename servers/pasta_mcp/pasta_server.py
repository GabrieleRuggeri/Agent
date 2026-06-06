import atexit
import os
import signal

from mcp.server.fastmcp import FastMCP

from pasta_prompts import how_to_make_pasta, how_to_properly_choose_ingredients
from pasta_resources import get_pasta_sample_image
from pasta_tools import get_bolognese_recipe, get_carbonara_recipe
from registry.mcp_registry import deregister_server, is_registry_configured, register_server

_host = os.environ.get("MCP_HOST", "0.0.0.0")
_port = int(os.environ.get("MCP_PORT", "8001"))
_server_name = os.environ.get("MCP_SERVER_NAME", "pasta-expert")

mcp = FastMCP(
    name="Pasta Expert",
    instructions="A pasta expert who can provide recipes, cooking tips, and pasta-related information",
    host=_host,
    port=_port,
)

# tools
mcp.add_tool(get_carbonara_recipe)
mcp.add_tool(get_bolognese_recipe)

# resources
mcp.resource("example://pasta_image")(get_pasta_sample_image)

# prompts
mcp.prompt("how_to_make_pasta")(how_to_make_pasta)
mcp.prompt("how_to_properly_choose_ingredients")(how_to_properly_choose_ingredients)


def _unregister() -> None:
    if is_registry_configured():
        deregister_server(_server_name)


def _register() -> None:
    if not is_registry_configured():
        return

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport != "streamable-http":
        return

    public_url = os.environ.get("MCP_PUBLIC_URL", f"http://localhost:{_port}/mcp")
    register_server(_server_name, public_url, transport)
    atexit.register(_unregister)

    def _handle_signal(signum, frame):
        _unregister()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def main():
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    _register()

    if transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
