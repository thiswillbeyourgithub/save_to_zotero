"""
Main CLI entry point for save_to_zotero.
"""

import sys
import fire
from .save_to_zotero import SaveToZotero


def main():
    """Main CLI entry point."""
    args = [arg.lower() for arg in sys.argv]
    helps = ["h", "help", "-h", "--help"]
    if any(h in args for h in helps):
        # detected help page wanted, so calling the class directly
        _ = fire.Fire(SaveToZotero)
    else:
        args, kwargs = fire.Fire((lambda *args, **kwargs: (args, kwargs)))
        _ = SaveToZotero(*args, **kwargs)
    return None


if __name__ == "__main__":
    main()
