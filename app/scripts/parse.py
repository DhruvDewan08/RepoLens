import sys 
from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import File , Function , Import ,FunctionCall
from app.parsing.functions import extract_functions
from app.parsing.imports import extract_imports
from app.parsing.calls import extract_calls

def main (repository_id: int):
    db = SessionLocal()

    files = db.query(File).filter_by(repository_id=repository_id).all() #reading what's already recorded in Postgres.
    # Clear old parse results for this repo before re-parsing,
    # so re-runs don't keep doubling counts.
    file_ids = [f.id for f in files]
    db.query(FunctionCall).filter(
        FunctionCall.caller_function_id.in_(
            db.query(Function.id).filter(Function.file_id.in_(file_ids))
        )
    ).delete(synchronize_session=False)
    db.query(Import).filter(Import.source_file_id.in_(file_ids)).delete(synchronize_session=False)
    db.query(Function).filter(Function.file_id.in_(file_ids)).delete(synchronize_session=False)
    db.commit()

    function_count = 0
    import_count = 0
    call_count = 0
    for file_row in files:
        full_path =Path("data/repos") /str(repository_id) /file_row.path
        # fixture repos aren't under data/repos, so fall back if that path doesn't exist
        if not full_path.exists():
            full_path =Path("tests/fixtures/shop") /file_row.path

        # Track qualified_name -> Function object for THIS file,
        # so we can link calls back to their caller below.
        
        qualified_name_to_function = {}

        for f in extract_functions(full_path):
            func_row=Function(
                file_id=file_row.id, #Each Function/Import row needs to point at a real file_id foreign key, and that id only exists because the file was already inserted into Postgres during ingestion.
                name=f["name"],
                qualified_name=f["qualified_name"],
                start_line=f["start_line"],
                end_line=f["end_line"],
                docstring=f["docstring"],
            )
            db.add(func_row)
            qualified_name_to_function[f["qualified_name"]] = func_row
            function_count += 1
        
        for i in extract_imports(full_path):
            db.add(Import(
                source_file_id=file_row.id,
                target_module =i["target_module"],
                imported_symbol=i["imported_symbol"],
            ))

            import_count += 1
        # Flush so the Function rows above get real ids assigned,
        # without doing a full commit yet.
        db.flush() #midddle ground: it sends the pending inserts to Postgres and gets real ids assigned to your Python objects (so func_row.id becomes a real number), without ending the transaction
        raw_calls = extract_calls(full_path)
        for c in raw_calls:
            caller = qualified_name_to_function.get(c["caller_qualified_name"])
            if caller is None:
                continue

            db.add(FunctionCall(
                caller_function_id=caller.id,
                callee_function_id=None,
                callee_name=c["callee_name"],
            ))
            call_count += 1
        
    db.commit()
    print(
        f"Parsed repository_id={repository_id}: "
        f"{function_count} functions, {import_count} imports, {call_count} raw calls"
        )
if __name__ == "__main__":
    main(int(sys.argv[1]))