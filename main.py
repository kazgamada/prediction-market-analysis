from __future__ import annotations

import sys
from pathlib import Path

from src.common.analysis import Analysis
from src.common.indexer import Indexer
from src.common.util import package_data
from src.common.util.strings import snake_to_title

try:
    from simple_term_menu import TerminalMenu
    _HAS_TERM_MENU = True
except (ImportError, NotImplementedError):
    TerminalMenu = None
    _HAS_TERM_MENU = False


def _select(options: list[str], title: str) -> int | None:
    if _HAS_TERM_MENU:
        menu = TerminalMenu(options, title=title, cycle_cursor=True, clear_screen=False)
        return menu.show()

    print(title)
    for i, opt in enumerate(options):
        print(f"  [{i}] {opt}")
    while True:
        raw = input("Enter number (or blank to exit): ").strip()
        if raw == "":
            return None
        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(options):
                return idx
        print(f"Invalid input. Enter 0-{len(options) - 1} or blank.")


def analyze(name: str | None = None):
    """Run analysis by name or show interactive menu."""
    analyses = Analysis.load()

    if not analyses:
        print("No analyses found in src/analysis/")
        return

    output_dir = Path("output")

    # If name provided, run that specific analysis
    if name:
        if name == "all":
            print("\nRunning all analyses...\n")
            for analysis_cls in analyses:
                instance = analysis_cls()
                print(f"Running: {instance.name}")
                saved = instance.save(output_dir, formats=["png", "pdf", "csv", "json", "gif"])
                for fmt, path in saved.items():
                    print(f"  {fmt}: {path}")
            print("\nAll analyses complete.")
            return

        # Find matching analysis
        for analysis_cls in analyses:
            instance = analysis_cls()
            if instance.name == name:
                print(f"\nRunning: {instance.name}\n")
                saved = instance.save(output_dir, formats=["png", "pdf", "csv", "json", "gif"])
                print("Saved files:")
                for fmt, path in saved.items():
                    print(f"  {fmt}: {path}")
                return

        # No match found
        print(f"Analysis '{name}' not found. Available analyses:")
        for analysis_cls in analyses:
            instance = analysis_cls()
            print(f"  - {instance.name}")
        sys.exit(1)

    # Interactive menu mode
    options = ["[All] Run all analyses"]
    for analysis_cls in analyses:
        instance = analysis_cls()
        options.append(f"{snake_to_title(instance.name)}: {instance.description}")
    options.append("[Exit]")

    choice = _select(options, "Select an analysis to run:")

    if choice is None or choice == len(options) - 1:
        print("Exiting.")
        return

    if choice == 0:
        # Run all analyses
        print("\nRunning all analyses...\n")
        for analysis_cls in analyses:
            instance = analysis_cls()
            print(f"Running: {instance.name}")
            saved = instance.save(output_dir, formats=["png", "pdf", "csv", "json", "gif"])
            for fmt, path in saved.items():
                print(f"  {fmt}: {path}")
        print("\nAll analyses complete.")
    else:
        # Run selected analysis
        analysis_cls = analyses[choice - 1]
        instance = analysis_cls()
        print(f"\nRunning: {instance.name}\n")
        saved = instance.save(output_dir, formats=["png", "pdf", "csv", "json", "gif"])
        print("Saved files:")
        for fmt, path in saved.items():
            print(f"  {fmt}: {path}")


def index():
    """Interactive indexer selection menu."""
    indexers = Indexer.load()

    if not indexers:
        print("No indexers found in src/indexers/")
        return

    # Build menu options
    options = []
    for indexer_cls in indexers:
        instance = indexer_cls()
        options.append(f"{snake_to_title(instance.name)}: {instance.description}")
    options.append("[Exit]")

    choice = _select(options, "Select an indexer to run:")

    if choice is None or choice == len(options) - 1:
        print("Exiting.")
        return

    indexer_cls = indexers[choice]
    instance = indexer_cls()
    print(f"\nRunning: {instance.name}\n")
    instance.run()
    print("\nIndexer complete.")


def package():
    """Package the data directory into a zstd-compressed tar archive."""
    success = package_data()
    sys.exit(0 if success else 1)


def main():
    if len(sys.argv) < 2:
        print("\nUsage: uv run main.py <command>")
        print("Commands: analyze, index, package")
        sys.exit(0)

    command = sys.argv[1]

    if command == "analyze":
        name = sys.argv[2] if len(sys.argv) > 2 else None
        analyze(name)
        sys.exit(0)

    if command == "index":
        index()
        sys.exit(0)

    if command == "package":
        package()
        sys.exit(0)

    print(f"Unknown command: {command}")
    print("Commands: analyze, index, package")
    sys.exit(1)


if __name__ == "__main__":
    main()
