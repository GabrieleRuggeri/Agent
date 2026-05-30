from mcp.server.fastmcp import FastMCP

from pasta_prompts import how_to_make_pasta, how_to_properly_choose_ingredients
from pasta_tools import get_carbonara_recipe, get_bolognese_recipe
from pasta_resources import get_pasta_sample_image

# Initialize FastMCP server
mcp = FastMCP(
    name = "Pasta Expert",
    instructions = "A pasta expert who can provide recipes, cooking tips, and pasta-related information",
)

# tools
mcp.add_tool(get_carbonara_recipe)
mcp.add_tool(get_bolognese_recipe)

# resources
mcp.resource("example://pasta_image")(get_pasta_sample_image)

# prompts
mcp.prompt("how_to_make_pasta")(how_to_make_pasta)
mcp.prompt("how_to_properly_choose_ingredients")(how_to_properly_choose_ingredients)

def main():
    # Initialize and run the server
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
