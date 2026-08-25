from app.db.session import SessionLocal
from app.db.models import File , Function , FunctionCall , Import

def resolve_calls(repository_id: int):
    db = SessionLocal()

    files = db.query(File).filter_by(repository_id=repository_id).all()

    #build lookup : file id -> {function_name: Function}
    functions_by_file = {}  #what functions exist in file X, by name.
    for file_row in files:
        funcs=db.query(Function).filter_by(file_id=file_row.id).all() # get all functions for this file
        functions_by_file[file_row.id] = {f.name: f for f in funcs} #build a dictionary of function names to Function objects for this file

    #build lookup : "module_stem" -> File (eg. "inventory" -> the inventory.py File row)
    file_by_stem = {}
    for file_row in files:
        stem = file_row.path.replace("\\", "/").split("/")[-1].removesuffix(".py") #removesuffix is a string method that removes the suffix from the string .this turns a path like inventory.py (or some/folder\\inventory.py on Windows) into just "inventory".
        file_by_stem[stem] = file_row #add the file row to the dictionary with the stem as the key , which file does module name Y correspond to
    
    #build lookup : file_id -> list of (target_module, imported_symbol)
    imports_by_file={}
    for file_row in files:
        imports_by_file[file_row.id] = db.query(Import).filter_by(source_file_id=file_row.id).all() #get all imports for this file

    resolved_count=0
    unresolved_count=0

    calls = (
        db.query(FunctionCall)
        .join(Function, FunctionCall.caller_function_id == Function.id)
        .filter(Function.file_id.in_([f.id for f in files]))
        .all()
    )

    for call in calls:
        caller = db.get(Function, call.caller_function_id) #get the Function object for the caller function
        name = call.callee_name

        if "." in name: #if the callee name contains a dot, it's not a simple function name, so we can't resolve it
            unresolved_count += 1 #increment the unresolved count
            continue

        same_file_funcs = functions_by_file.get(caller.file_id, {}) #get the functions for the caller file
        if name in same_file_funcs: #if the callee name is in the same file as the caller
            call.callee_function_id = same_file_funcs[name].id
            resolved_count += 1
            continue

        found = False
        for imp in imports_by_file.get(caller.file_id, []):
            if imp.imported_symbol == name:
                module_stem = imp.target_module.split(".")[-1]
                target_file = file_by_stem.get(module_stem)
                if target_file:
                    target_funcs = functions_by_file.get(target_file.id, {})
                    if name in target_funcs:
                        call.callee_function_id = target_funcs[name].id
                        resolved_count += 1
                        found = True
                        break
        if not found:
            unresolved_count += 1

    db.commit()
    print(f"Resolved {resolved_count} calls, {unresolved_count} left unresolved")


if __name__ == "__main__":
    import sys
    resolve_calls(int(sys.argv[1]))