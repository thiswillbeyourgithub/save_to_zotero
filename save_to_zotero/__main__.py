"""
Main CLI entry point for save_to_zotero.
"""

import sys
import fire
from .save_to_zotero import SaveToZotero


def main():
    """Main CLI entry point."""
    fire.Fire(SaveToZotero)


if __name__ == "__main__":
    sys.exit(main())
