# MCP server Dockerfile for Claude Desktop integration
FROM ghcr.io/astral-sh/uv:0.6.6-python3.13-bookworm

# Metadata label for Docker MCP Gateway (required for local development)
LABEL io.docker.server.metadata='{"name":"hass-mcp-plus","description":"Home Assistant MCP server for smart home control","command":["python","-m","app"],"secrets":[{"name":"hass-mcp-plus.ha_token","env":"HA_TOKEN"},{"name":"hass-mcp-plus.ha_url","env":"HA_URL"},{"name":"hass-mcp-plus.tz","env":"TZ"},{"name":"hass-mcp-plus.ha_verify_ssl","env":"HA_VERIFY_SSL"}]}'

# Create non-root user for security
RUN groupadd -r mcp && useradd -r -g mcp mcp

# Set working directory
WORKDIR /app

# Copy only necessary files (see .dockerignore for exclusions)
COPY pyproject.toml README.md LICENSE ./
COPY app/ ./app/

# Set environment for MCP communication
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install package with UV (regular install, not editable)
RUN uv pip install --system .

# Change ownership and switch to non-root user
RUN chown -R mcp:mcp /app
USER mcp

# Run the MCP server with stdio communication using the module directly
ENTRYPOINT ["python", "-m", "app"]