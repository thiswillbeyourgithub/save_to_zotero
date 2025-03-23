"""
save_to_zotero - Save webpages as PDFs and add them to Zotero.
"""

from . import utils
from .save_to_zotero import SaveToZotero

__version__ = SaveToZotero.VERSION

__all__ = ["SaveToZotero", "utils"]

