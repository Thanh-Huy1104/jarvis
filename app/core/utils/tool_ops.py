import re
import importlib.util
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def _strip_structural_markers(text: str) -> str:
    """
    Strips raw code blocks (Python/JSON) and standalone JSON patterns from the text
    to keep the final output clean for the user.
    """
    # Remove markdown blocks
    text = re.sub(r'```(?:python|json)\n.*?\n```', '', text, flags=re.DOTALL)
    # Remove standalone JSON tool patterns: {"tools": [...]}
    # Use non-greedy matching .*? inside
    text = re.sub(r'\{.*?"tools":\s*\[.*?\].*?\}', '', text, flags=re.DOTALL)
    return text.strip()

def _load_tool_function(tool_name: str, registry):
    """
    Dynamically loads a tool function from the library using the registry's file path.
    """
    try:
        tool_def = registry.get_tool(tool_name)
        if not tool_def:
            logger.error(f"Tool '{tool_name}' not found in registry.")
            return None
            
        spec = importlib.util.spec_from_file_location(tool_name, tool_def.file_path)
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, tool_name, None)
    except Exception as e:
        logger.error(f"Failed to load tool {tool_name}: {e}")
        return None

def _execute_tool_calls(tool_calls: List[Dict[str, Any]], registry) -> str:
    """
    Executes a list of tool calls locally and returns the combined output.
    """
    results = []
    for call in tool_calls:
        name = call.get("name")
        args = call.get("args", {})
        
        func = _load_tool_function(name, registry)
        if not func:
            results.append(f"Error: Tool '{name}' not found or could not be loaded.")
            continue
            
        try:
            logger.info(f"Executing Tool: {name}({args})")
            # Call the function with arguments
            output = func(**args)
            results.append(f"Tool '{name}' Output:\n{output}")
        except Exception as e:
            results.append(f"Error executing '{name}': {e}")
            
    return "\n\n".join(results)
