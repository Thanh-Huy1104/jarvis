# Jarvis Skills + MCP Integration

## Overview

Jarvis now uses a **skills-first architecture** with MCP tools as a fallback for system-level operations.

## What Changed

### 1. Skills System (`~/.jarvis/skills/`)

**Created 5 core skill files:**
- `web_search.md` - DuckDuckGo web search with DDGS
- `news_search.md` - News article search  
- `system_monitoring.md` - CPU, memory, disk monitoring with psutil
- `data_analysis.md` - CSV analysis with pandas
- `web_scraping.md` - HTML parsing with BeautifulSoup

**Auto-loading:**
- `SkillLibrary` scans `~/.jarvis/skills/*.md` on startup
- Parses markdown format (title, description, code blocks)
- Loads into ChromaDB for semantic search
- Skills retrieved automatically when relevant to user queries

### 2. MCP Integration

**Essential MCP Server** (`servers/desktop/server_essential.py`):
- Minimal toolset for host system access only
- Tools: `list_directory`, `read_file`, `write_file`, `run_shell_command`, `manage_docker`
- Replaced bloated `server.py` with 200+ lines

**Engine Integration:**
- Added `JarvisMCPClient` to `JarvisEngine.__init__`
- New node: `call_mcp_tools()` for MCP tool execution
- Helper: `_extract_json()` for parsing tool calls
- Cleanup: `cleanup()` method for MCP connections

**Updated Prompts:**
- System capabilities now explain both Python sandbox AND MCP tools
- Clear decision guide: "Default to Python sandbox for 90% of tasks"
- LLM instructed to avoid generating Python code when MCP is needed

### 3. Configuration

**`mcp_servers.json`:**
```json
{
  "servers": {
    "desktop_essential": {
      "description": "Essential host system tools (filesystem, shell, docker)",
      "command": "uv",
      "args_template": ["run", "{script}"],
      "script": "servers/desktop/server_essential.py",
      "enabled": true
    }
  }
}
```

**`requirements.txt`:**
- Added `mcp` package for Model Context Protocol client

### 4. Documentation

**Created:**
- `~/.jarvis/SKILLS_VS_MCP.md` - Philosophy and usage guide
- Updated `engine.py` docstring with skills vs MCP philosophy

## How It Works

### For Most Tasks (Python Sandbox):
1. User asks question
2. `SkillLibrary.find_top_skills()` searches ChromaDB semantically
3. Relevant skills added to LLM prompt
4. LLM generates/adapts Python code
5. Code executes in Docker sandbox
6. Results returned to user

### For Host System Tasks (MCP):
1. User requests host operation (e.g., "list files in ~/Documents")
2. LLM recognizes need for MCP tools
3. `call_mcp_tools()` node activated
4. LLM generates tool call JSON
5. MCP client executes tool on host
6. Results returned to user

## Usage Examples

### Skills (Automatic)
```
User: "Search for Python tutorials"
→ Finds web_search.md skill
→ Generates code with DDGS().text()
→ Executes in sandbox
```

### MCP Tools (When Needed)
```
User: "Show me files in my home directory"
→ Recognizes host filesystem access needed
→ Calls list_directory MCP tool
→ Returns host directory listing
```

## Adding New Skills

1. Create `~/.jarvis/skills/my_skill.md`:
```markdown
# My Skill Title

Description of what it does.

## Code

\`\`\`python
# Your Python code here
\`\`\`
```

2. Reset ChromaDB: `rm -rf db/chroma`
3. Restart Jarvis

## Testing

```bash
# Test skill loading
cd /home/th/jarvis-agent
source .venv/bin/activate
python -c "from app.core.skills import SkillLibrary; s = SkillLibrary(); print(f'Loaded {s.collection.count()} skills')"

# Test MCP client
python -c "from app.adapters.mcp_client import JarvisMCPClient; print('✓ MCP client working')"

# Test engine initialization
python -c "from app.core.engine import JarvisEngine; e = JarvisEngine(); print('✓ Engine initialized')"
```

## Architecture Benefits

1. **Separation of Concerns**: Skills for computation, MCP for system access
2. **Safety**: Most code runs in isolated sandbox
3. **Extensibility**: Add skills by creating markdown files
4. **Efficiency**: Semantic search finds relevant code automatically
5. **Maintainability**: MCP server reduced from 550 to 200 lines

## Next Steps

- Add more skills to `~/.jarvis/skills/` for common tasks
- Test MCP tool calling in actual workflow
- Monitor skill usage to identify frequently-used patterns
- Consider skill versioning for iterative improvements
