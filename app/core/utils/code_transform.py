"""Code transformation utilities for improving code execution"""

import ast
import logging

logger = logging.getLogger(__name__)


def ensure_print_output(code: str) -> str:
    """
    Ensures code has print statements for visibility.
    If the code defines functions but doesn't call/print them, add calls.
    
    Args:
        code: Python code string
        
    Returns:
        Modified code with guaranteed output
    """
    try:
        # Parse the code
        tree = ast.parse(code)
        
        # Check if code has any print statements
        has_prints = any(
            isinstance(node, ast.Expr) and 
            isinstance(node.value, ast.Call) and
            (isinstance(node.value.func, ast.Name) and node.value.func.id == 'print')
            for node in ast.walk(tree)
        )
        
        # If already has prints, return as-is
        if has_prints:
            return code
        
        # Check for function definitions that aren't called
        functions_defined = []
        function_calls = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions_defined.append(node.name)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    function_calls.add(node.func.id)
        
        # Find functions that are defined but never called
        uncalled_functions = [f for f in functions_defined if f not in function_calls]
        
        # If there's a main-looking function (common pattern), call it
        main_candidates = ['main', 'run', uncalled_functions[0] if uncalled_functions else None]
        
        for candidate in main_candidates:
            if candidate in uncalled_functions:
                logger.info(f"Adding call to uncalled function: {candidate}()")
                code += f"\n\n# Auto-added to show output\nresult = {candidate}()\nif result is not None:\n    print(result)"
                return code
        
        # If there are variable assignments but no prints, print the last one
        assignments = [
            node.targets[0].id 
            for node in tree.body 
            if isinstance(node, ast.Assign) and 
               isinstance(node.targets[0], ast.Name)
        ]
        
        if assignments:
            last_var = assignments[-1]
            logger.info(f"Adding print for last assignment: {last_var}")
            code += f"\n\n# Auto-added to show output\nprint({last_var})"
            return code
        
        return code
        
    except Exception as e:
        logger.warning(f"Could not parse/modify code for print injection: {e}")
        return code
