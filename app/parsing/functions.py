import ast
from pathlib import Path


def extract_functions(file_path):
    """
    Parses a single Python file and returns a list of dicts,
    one per function/method found, with name, qualified name,
    and line range.
    """
    file_path = Path(file_path)
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    functions = []

    for node in ast.walk(tree): #visits every single node in the tree at every depth one at a time 
        if isinstance(node, ast.ClassDef): #checks if the node is a class definition
            class_name = node.name
            for child in node.body: #just class direct children not the whole body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)): #filters down to only nodes that represent function definitions , checks if the node is a function or an asynchronous function
                    functions.append({
                        "name": child.name,
                        "qualified_name": f"{class_name}.{child.name}", #the qualified name is the class name plus the function name
                        "start_line": child.lineno,
                        "end_line": child.end_lineno,
                        "docstring": ast.get_docstring(child), #gets the docstring from the function
                    })

    for node in tree.body: #the top level statements of the whole file , not nested inside anything . catches files that live directly in the file and not in any class  
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): #filters down to only nodes that represent function definitions , checks if the node is a function or an asynchronous function
            functions.append({
                "name": node.name,
                "qualified_name": node.name, #since its top level , the qualified name is the same as the name , no clas prefix needed 
                "start_line": node.lineno,
                "end_line": node.end_lineno,
                "docstring": ast.get_docstring(node), #gets the docstring from the function
            })

    return functions