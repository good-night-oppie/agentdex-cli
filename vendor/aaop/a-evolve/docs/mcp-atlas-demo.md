# Running MCP-Atlas Evolution — Demo Guide

This guide walks you through running the MCP-Atlas evolve loop using `uv` for environment management and setup API keys for different servers.

The [MCP-Atlas](https://github.com/scaleapi/mcp-atlas) benchmark evaluates agents on tool-calling tasks via the Model Context Protocol (MCP). The benchmark provides a Docker image (`ghcr.io/scaleapi/mcp-atlas`) that bundles all MCP server binaries and their dependencies. MCP servers communicate over stdio transport, routed through Docker via `docker exec -i`.

## Prerequisites

| Requirement | Why |
|---|---|
| Python ≥ 3.11 | Runtime |
| [uv](https://docs.astral.sh/uv/) | Fast Python env & package manager |
| [Docker](https://docs.docker.com/get-docker/) | MCP-Atlas runs MCP servers inside Docker containers |
| AWS credentials **or** `ANTHROPIC_API_KEY` | LLM access for both the MCP agent (solver) and the evolver |

The MCP agent uses **strands-agents** with **Bedrock Claude Sonnet** (`us.anthropic.claude-sonnet-4-20250514`) by default. If you prefer the Anthropic API directly, pass `--provider anthropic`.

## 1. Environment Setup with uv

```bash
# Clone the repo (if you haven't)
git clone <repo-url> && cd agent-evolve

# Create a virtual environment
uv venv .venv --python 3.11

# Install with MCP dependencies
uv pip install -e ".[mcp,dev]"

# Verify
uv run python -c "import agent_evolve; print('OK')"
```

## 2. Docker Setup

MCP-Atlas requires a Docker image that bundles all MCP server binaries and their dependencies.

```bash
# Verify Docker is running
docker info > /dev/null 2>&1 && echo "Docker OK" || echo "Docker not running"

# Pull the MCP-Atlas image
docker pull ghcr.io/scaleapi/mcp-atlas:latest

# Verify the image is available
docker image inspect ghcr.io/scaleapi/mcp-atlas:latest > /dev/null 2>&1 && echo "Image OK"
```

The image is pulled automatically by the agent if not present locally, but pre-pulling avoids delays during your first run.

## 3. Configure Credentials

### AWS Bedrock (default)

The MCP agent calls Bedrock via `strands-agents`. The evolver also defaults to Bedrock.

```bash
# Either use AWS CLI profiles or export directly:
export AWS_DEFAULT_REGION=us-west-2

# Verify Bedrock access
aws bedrock-runtime invoke-model \
  --model-id us.anthropic.claude-sonnet-4-20250514-v1:0 \
  --content-type application/json \
  --accept application/json \
  --body "$(echo -n '{"messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}],"max_tokens":10,"anthropic_version":"bedrock-2023-05-31"}' | base64 -w 0)" \
  /dev/stdout 2>&1 | head -20 && echo "Bedrock OK"
```

### MCP Server API Keys

Many MCP-Atlas tasks require third-party API keys for the MCP servers they use (Brave Search, GitHub, Slack, Google Maps, etc.). The `KeyRegistry` loads keys from multiple sources and injects them into the Docker container at startup. Tasks whose keys are missing are automatically filtered out.

#### Built-in server-to-key mapping

The full mapping lives in [`agent_evolve/agents/mcp/server_keys.yaml`](../agent_evolve/agents/mcp/server_keys.yaml) and covers all 36 official MCP-Atlas servers. The 16 servers that require API keys are listed below (sorted by task frequency in the benchmark):

| MCP Server | Required Env Var(s) | % Tasks | Notes |
|---|---|---|---|
| `exa` | `EXA_API_KEY` | 13% | [Exa Search](https://exa.ai/) |
| `airtable` | `AIRTABLE_API_KEY` | 12% | [Airtable MCP](https://github.com/felores/airtable-mcp) ⚠️ requires [data import](https://github.com/scaleapi/mcp-atlas/blob/main/data_exports/README.md) |
| `mongodb` | `MONGODB_CONNECTION_STRING` | 12% | Append `?tls=true` for Docker. ⚠️ requires [data import](https://github.com/scaleapi/mcp-atlas/blob/main/data_exports/README.md) |
| `oxylabs` | `OXYLABS_USERNAME`, `OXYLABS_PASSWORD` | 11% | [Oxylabs Scraper API](https://oxylabs.io/products/scraper-api/web) |
| `brave-search` | `BRAVE_API_KEY` | 10% | [Brave Search API](https://brave.com/search/api/) |
| `alchemy` | `ALCHEMY_API_KEY` | 8% | [Alchemy API](https://www.alchemy.com/docs/) |
| `national-parks` | `NPS_API_KEY` | 8% | [National Park Service API](https://www.nps.gov/subjects/developer/get-started.htm) |
| `twelvedata` | `TWELVE_DATA_API_KEY` | 8% | [Twelve Data API](https://twelvedata.com/docs) |
| `lara-translate` | `LARA_ACCESS_KEY_ID`, `LARA_ACCESS_KEY_SECRET` | 7% | [Lara Translate API](https://developers.laratranslate.com/docs/introduction) |
| `notion` | `NOTION_TOKEN` | 6% | [Notion MCP Server](https://github.com/makenotion/notion-mcp-server) ⚠️ requires [data import](https://github.com/scaleapi/mcp-atlas/blob/main/data_exports/README.md) |
| `weather-data` | `WEATHER_API_KEY` | 6% | [WeatherAPI](https://www.weatherapi.com/) |
| `github` | `GITHUB_TOKEN` | 5% | [GitHub PAT](https://github.com/settings/tokens) |
| `slack` | `SLACK_MCP_XOXC_TOKEN`, `SLACK_MCP_XOXD_TOKEN` | 5% | [Slack MCP Server](https://github.com/korotovsky/slack-mcp-server/blob/master/docs/01-authentication-setup.md) ⚠️ requires [data import](https://github.com/scaleapi/mcp-atlas/blob/main/data_exports/README.md) |
| `google-maps` | `GOOGLE_MAPS_API_KEY` | 5% | [Google Maps Platform](https://developers.google.com/maps) |
| `e2b-server` | `E2B_API_KEY` | 5% | [E2B Code Interpreter](https://e2b.dev/) |
| `google-workspace` | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | 4% | [Google Workspace Server](https://www.npmjs.com/package/@geobio/google-workspace-server#prerequisites) ⚠️ requires [data import](https://github.com/scaleapi/mcp-atlas/blob/main/data_exports/README.md) |

The remaining 20 servers (arxiv, calculator, cli-mcp-server, context7, ddg-search, desktop-commander, fetch, filesystem, git, mcp-code-executor, mcp-server-code-runner, memory, met-museum, open-library, osm-mcp-server, pubmed, weather, whois, wikipedia, clinicaltrialsgov-mcp-server) require no API keys.

You can extend the mapping by editing `server_keys.yaml` directly or providing a custom YAML file (see [Custom server-key map](#custom-server-key-map) below).

#### Option A: `.env` file (recommended for local dev)

Create a `.env` file in the project root (already in `.gitignore`):

```bash
# .env
BRAVE_API_KEY=brv-xxxxxxxxxxxx
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
SLACK_MCP_XOXC_TOKEN=xoxc-xxxxxxxxxxxx
SLACK_MCP_XOXD_TOKEN=xoxd-xxxxxxxxxxxx
GOOGLE_MAPS_API_KEY=AIzaxxxxxxxxxxxx
GOOGLE_CLIENT_ID=xxxxxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxx
GOOGLE_REFRESH_TOKEN=1//xxxxxxxxxxxx
NOTION_TOKEN=ntn_xxxxxxxxxxxx
MONGODB_CONNECTION_STRING=mongodb+srv://user:pass@cluster.mongodb.net/?tls=true
ALCHEMY_API_KEY=xxxxxxxxxxxx
E2B_API_KEY=e2b_xxxxxxxxxxxx
EXA_API_KEY=xxxxxxxxxxxx
LARA_ACCESS_KEY_ID=xxxxxxxxxxxx
LARA_ACCESS_KEY_SECRET=xxxxxxxxxxxx
NPS_API_KEY=xxxxxxxxxxxx
OXYLABS_USERNAME=xxxxxxxxxxxx
OXYLABS_PASSWORD=xxxxxxxxxxxx
TWELVE_DATA_API_KEY=xxxxxxxxxxxx
WEATHER_API_KEY=xxxxxxxxxxxx
```

Then pass it via the `--env-file` flag or the `MCP_ENV_FILE` environment variable:

```bash
# Via CLI flag
uv run python examples/mcp_examples/adaptive_evolve_all.py \
  --env-file .env \
  --docker-image ghcr.io/scaleapi/mcp-atlas:latest


# Or via environment variable
export MCP_ENV_FILE=.env
uv run python examples/mcp_examples/adaptive_evolve_all.py \
  --docker-image ghcr.io/scaleapi/mcp-atlas:latest
```

#### Option B: Process environment variables

Export keys directly in your shell. These take the highest priority and override `.env` and AWS values:

```bash
export BRAVE_API_KEY=brv-xxxxxxxxxxxx
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
export NOTION_TOKEN=ntn_xxxxxxxxxxxx

uv run python examples/mcp_examples/adaptive_evolve_all.py \
  --docker-image ghcr.io/scaleapi/mcp-atlas:latest
```

#### Option C: AWS Secrets Manager (for shared/CI environments)

Store keys as a JSON secret in AWS Secrets Manager:

```json
{
  "BRAVE_API_KEY": "brv-xxxxxxxxxxxx",
  "GITHUB_TOKEN": "ghp-xxxxxxxxxxxx",
  "SLACK_MCP_XOXC_TOKEN": "xoxc-xxxxxxxxxxxx",
  "SLACK_MCP_XOXD_TOKEN": "xoxd-xxxxxxxxxxxx",
  "NOTION_TOKEN": "ntn_xxxxxxxxxxxx",
  "GOOGLE_MAPS_API_KEY": "AIzaxxxxxxxxxxxx"
}
```

Then reference it in your YAML config:

```yaml
# evolve_config.yaml
mcp_aws_secret_name: my-org/mcp-api-keys
mcp_aws_region: us-west-2
```

#### Key source priority

When the same key exists in multiple sources, the highest-priority source wins:

1. Process environment variables (highest)
2. `.env` file
3. AWS Secrets Manager (lowest)

#### Custom server-key map

To add servers not in the built-in defaults, create a YAML file:

```yaml
# mcp_server_keys.yaml
brave-search:
  - BRAVE_API_KEY
github:
  - GITHUB_TOKEN
my-custom-server:
  - MY_CUSTOM_API_KEY
  - MY_CUSTOM_SECRET
```

Pass it via config:

```yaml
# evolve_config.yaml
mcp_server_key_map: mcp_server_keys.yaml
```

#### Task filtering

When keys are loaded, the benchmark automatically filters tasks:

- Tasks whose MCP servers have all required keys available → included
- Tasks whose servers need no keys (e.g. `filesystem`, `fetch`) → always included
- Tasks with missing keys → filtered out with an INFO log

If all tasks are filtered out, a WARNING is logged listing every missing env var.

#### EvolveConfig.extra keys reference

| Key | Type | Default | Description |
|---|---|---|---|
| `mcp_env_file` | `str` | `".env"` | Path to `.env` file (also settable via `MCP_ENV_FILE` env var) |
| `mcp_aws_secret_name` | `str` | `None` | AWS Secrets Manager secret name |
| `mcp_aws_region` | `str` | `None` | AWS region for Secrets Manager |
| `mcp_server_key_map` | `str` | `None` | Path to custom YAML server-to-key mapping |

## 4. Data Exports
There are five servers require both API keys AND sample data to be uploaded to your account. Please refer to **MCP-Atlas GitHub**: <https://github.com/scaleapi/mcp-atlas/blob/main/data_exports/README.md> for the details.

## References

- **MCP-Atlas GitHub**: <https://github.com/scaleapi/mcp-atlas>
- **MCP-Atlas HuggingFace Dataset**: [`ScaleAI/MCP-Atlas`](https://huggingface.co/datasets/ScaleAI/MCP-Atlas)
- **Model Context Protocol**: <https://modelcontextprotocol.io>
