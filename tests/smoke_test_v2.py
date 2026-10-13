import sys
import importlib
from pathlib import Path

def test_imports():
    base_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(base_dir))
    
    dirs_to_check = ['core', 'actions']
    errors = []
    
    for d in dirs_to_check:
        dir_path = base_dir / d
        if not dir_path.exists():
            continue
            
        for f in dir_path.glob("*.py"):
            if f.name == "__init__.py":
                continue
                
            module_name = f"{d}.{f.stem}"
            try:
                importlib.import_module(module_name)
            except ImportError as e:
                errors.append(f"{module_name}: {e}")
            except Exception as e:
                # Other exceptions during import (e.g. syntax errors or missing config) are still errors
                errors.append(f"{module_name}: {type(e).__name__} - {e}")
                
    if errors:
        print("Import Errors found:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("All imports succeeded!")

if __name__ == "__main__":
    test_imports()
