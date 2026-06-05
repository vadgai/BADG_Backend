"""Quick syntax check for all modified files."""
import ast, sys, os

files = [
    "app.py",
    "diagnosis_rule_engine.py",
    "diagnosis_rule_engine_v5.py",
    os.path.join("diagnosis_report", "report.py"),
    os.path.join("diagnosis_methods", "state_followup.py"),
    "symptom_extractor.py",
]

all_ok = True
for f in files:
    try:
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        ast.parse(src)
        print(f"OK: {f}")
    except SyntaxError as e:
        print(f"SYNTAX ERROR in {f}: {e}")
        all_ok = False
    except FileNotFoundError:
        print(f"NOT FOUND: {f}")

sys.exit(0 if all_ok else 1)
