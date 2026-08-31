from app.db.session import SessionLocal
from app.db.models import Function, FunctionCall

def get_callers(function_id: int): #returns a list of Function objects that call the given function -function is the callee
    db = SessionLocal()
    calls= db.query(FunctionCall).filter_by(callee_function_id = function_id).all()
    return [db.get(Function, c.caller_function_id) for c in calls]

def get_callees(function_id: int): #returns a list of Function objects that are called by the given function - function is the caller (mirror case)
    db = SessionLocal()
    calls= db.query(FunctionCall).filter_by(caller_function_id = function_id).all()
    return [db.get(Function, c.callee_function_id) for c in calls if c.callee_function_id is not None] #filter out unresolved calls like maths.ceil - they get excluded

def get_callers_bfs(function_id: int, depth: int = 3):
    """
    Returns all functions that (directly or indirectly) call the given function,
    up to `depth` hops away, along with how many hops away each one is.
    """
    visited = {function_id: 0} #dictionary tracking every function id we've reached so far, and how many hops away it is
    frontier = [function_id] 
    current_depth = 0

    while frontier and current_depth < depth: # capped at 2-3 hops for now while there are still functions to explore and we haven't reached the depth limit
        next_frontier = []
        for fid in frontier:
            for caller in get_callers(fid):
                if caller.id not in visited: #if we haven't seen this function before, add it to the visited dictionary and the frontier
                    visited[caller.id] = current_depth + 1
                    next_frontier.append(caller.id)
        frontier = next_frontier #update frontier to the next level of functions
        current_depth += 1

    db = SessionLocal()
    results = []
    for fid, hop in visited.items(): #only return functions that are not the original function itself
        if fid == function_id:
            continue
        results.append((db.get(Function, fid), hop))
    return results

def get_callees_bfs(function_id: int, depth: int = 3):
    """
    Returns all functions that the given function (directly or indirectly) calls,
    up to `depth` hops away, along with how many hops away each one is.
    """
    visited = {function_id: 0}
    frontier = [function_id]
    current_depth = 0

    while frontier and current_depth < depth:
        next_frontier = []
        for fid in frontier:
            for callee in get_callees(fid):
                if callee.id not in visited:
                    visited[callee.id] = current_depth + 1
                    next_frontier.append(callee.id)
        frontier = next_frontier
        current_depth += 1

    db = SessionLocal()
    results = []
    for fid, hop in visited.items():
        if fid == function_id:
            continue
        results.append((db.get(Function, fid), hop))
    return results