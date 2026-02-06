import pyslang
from typing import Union, List, Dict, Any

# The file is first parsed into a syntax tree, then added to a Compilation, where slang resolves classes, 
# variables, types, and constraints into real symbols. By walking the compilation with a visitor, 
# the script observes when a class is encountered and then records every variable (VariableSymbol) and 
# constraint block (ConstraintBlockSymbol) the compiler associates with that class. This lets you reliably 
# extract fields, their types, and whether they are rand, as well as the names of constraint blocks, even if 
# UVM macros are undefined.

class AllClassesExtractor:
    """Collect fields and constraint blocks for all classes in the file,
    using a simple 'current class' tracking approach."""

    def __init__(self):
        # classes[name] = {"fields": [...], "constraints": [...]}
        self.classes: Dict[str, Dict[str, List[Any]]] = {}
        self.current_class: str | None = None

    def _ensure_class(self, class_name: str):
        if class_name not in self.classes:
            self.classes[class_name] = {
                "fields": [],
                "constraints": [],
            }

    def __call__(self, obj: Union[pyslang.Token, pyslang.SyntaxNode]):
        # When we see a class, mark it as the "current" one
        if isinstance(obj, pyslang.ClassType):
            self.current_class = obj.name
            self._ensure_class(obj.name)

        # While we're "in" a class, collect all VariableSymbols we encounter
        if self.current_class is not None and isinstance(obj, pyslang.VariableSymbol):
            rand_mode = getattr(obj, "randMode", None)
            rand_name = rand_mode.name if rand_mode is not None else "None"

            self.classes[self.current_class]["fields"].append(
                {
                    "name": obj.name,
                    "type": str(obj.type),
                    "rand_mode": rand_name,
                }
            )

        # While we're "in" a class, collect all constraint blocks
        if self.current_class is not None and isinstance(obj, pyslang.ConstraintBlockSymbol):
            self.classes[self.current_class]["constraints"].append(obj)


def parse_file(filepath: str) -> Dict[str, Dict[str, List[Any]]]:
    """Parse the file and return a dict of class_name -> {fields, constraints}."""

    tree = pyslang.SyntaxTree.fromFile(filepath)
    compilation = pyslang.Compilation()
    compilation.addSyntaxTree(tree)

    # Show diagnostics but don't fail on them
    diags = compilation.getAllDiagnostics()
    if diags:
        print("Diagnostics from slang:")
        for d in diags:
            print("  ", d)
        print("  (Ignoring diagnostics and continuing)\n")

    extractor = AllClassesExtractor()
    compilation.getRoot().visit(extractor)
    classes = extractor.classes

    # Convert ConstraintBlockSymbols to simple info (name only for now)
    for cname, info in classes.items():
        blocks = info["constraints"]
        info["constraints"] = [{"name": b.name} for b in blocks]

    return classes


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="SystemVerilog file")
    parser.add_argument(
        "--out",
        default=None,
        help="Output text file (default: <input>_summary.txt)",
    )
    args = parser.parse_args()

    classes = parse_file(args.file)

    if not classes:
        print("No classes found in file.")
        return

    # Decide output filename
    if args.out:
        out_file = args.out
    else:
        base = os.path.splitext(os.path.basename(args.file))[0]
        out_file = f"{base}_summary.txt"

    with open(out_file, "w", encoding="utf-8") as f:
        for class_name in sorted(classes.keys()):
            info = classes[class_name]
            fields = info["fields"]
            constraints = info["constraints"]

            f.write(f"Class: {class_name}\n\n")

            f.write("Fields:\n")
            if fields:
                for fld in fields:
                    f.write(
                        f"  {fld['name']:12s} : {fld['type']:20s}  "
                        f"rand_mode={fld['rand_mode']}\n"
                    )
            else:
                f.write("  <no fields found>\n")

            f.write("\nConstraints:\n")
            if constraints:
                for block in constraints:
                    f.write(f"  block {block['name']}\n")
            else:
                f.write("  <no constraints found>\n")


    print(f"Wrote summary to {out_file}")


if __name__ == "__main__":
    main()
