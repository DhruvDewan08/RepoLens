"""
    Given an ast.Call node, returns the name being called as a string.
    Handles both simple calls (foo()) and attribute calls (obj.method()).
"""

import ast 
from pathlib import Path 

def _get_call_name(call_node):
    func= call_node.func #tells whats being called 

    
    if isinstance(func , ast.Name):
        return func.id

    if isinstance(func , ast.Attribute): #for eg obj.method() or math.ceil(x)
        part =[]
        node =func
        while isinstance(node , ast.Attribute): #walks down the chain collecting each piece untill it hits the base Name at the bottom 
            part.append(node.attr)
            node =node.value
        if isinstance(node , ast.Name):
            part.append(node.id)
        return '.'.join(reversed(part)) #joins the parts together with a dot
    return None

def _extract_calls_from_function(func_node, qualified_name):
    calls= []
    for node in ast.walk(func_node): #tells which function is the caller and which function is the callee
        if isinstance(node, ast.Call):
            name= _get_call_name(node) #gets the name of the function being called
            if name:
                calls.append({
                    "caller_qualified_name": qualified_name,
                    "callee_name": name,
                    "line": node.lineno,

                })
    return calls

def extract_calls(file_path): #classes first then top level functions 
    file_path =Path(file_path)
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls= []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified= f"{class_name}.{child.name}"
                    calls.extend(_extract_calls_from_function(child, qualified))
    
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls.extend(_extract_calls_from_function(node, node.name))
    return calls