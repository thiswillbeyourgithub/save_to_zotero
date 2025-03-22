"""
Script to save webpages as PDFs and add them to Zotero.
Uses playwright for PDF generation and pyzotero for Zotero integration.
"""

import hashlib
import json
import os
import tempfile
import subprocess
import time
from datetime import datetime
from typing import Dict, Optional, Tuple, Any, Union, List
import requests
import fire
import shutil
from pyzotero import zotero
from playwright.sync_api import sync_playwright
from pathlib import Path
from urllib.parse import urlparse
import io
import PyPDF2
from loguru import logger
from requests.exceptions import RequestException
from utils.misc import (
    find_available_port,
    extract_key,
    configure_logger,
    ensure_zotero_running,
)
from utils.webpage import (
    save_webpage_as_pdf,
    get_webpage_metadata,
    SimpleHTTPServerThread,
)

# Configure module logger
configure_logger(__name__)


class ZoteroUploader:
    """
    Class for uploading webpages to Zotero as PDF attachments.
    """

    VERSION: str = "0.1.0"

    def __init__(
        self,
        url: Optional[str] = None,
        pdf_path: Optional[str] = None,
        storage_dir: str = os.path.expanduser("~/Zotero/storage"),
        wait: int = 5000,
        api_key: Optional[str] = None,
        library_id: Optional[str] = None,
        library_type: str = "user",
        collection: Optional[str] = None,
        collection_name: Optional[str] = None,
        verbose: bool = False,
        use_snapshot: bool = True,
    ):
        """
        Save a webpage as PDF and add it to Zotero, or add an existing PDF file.

        Args:
            url: The URL of the webpage to save (optional if pdf_path is provided)
            pdf_path: Path to an existing PDF file to add (optional if url is provided)
            storage_dir: Directory where PDFs should be saved
            wait: Time to wait (ms) for the page to fully load (for URLs)
            api_key: Zotero API key (defaults to ZOTERO_API_KEY environment variable if not provided)
            library_id: Zotero library ID (defaults to ZOTERO_LIBRARY_ID environment variable if not provided)
            library_type: Zotero library type (must be "user" or "group", defaults to ZOTERO_LIBRARY_TYPE if set)
            collection: Collection key to add the item to (defaults to ZOTERO_COLLECTION environment variable if not provided)
            collection_name: Collection name to add the item to (will search for a collection with this name)
            verbose: Enable verbose logging
            use_snapshot: Use Zotero connector's saveSnapshot feature when saving URLs (default: True)

        """
        if not url and not pdf_path:
            raise ValueError("Either url or pdf_path must be provided")

        if url and pdf_path:
            logger.warning("Both URL and PDF path provided; PDF path will be used")

        # Make sure Zotero is running
        ensure_zotero_running()

        api_key = api_key or os.environ.get("ZOTERO_API_KEY")
        library_id = library_id or os.environ.get("ZOTERO_LIBRARY_ID")
        library_type = library_type or os.environ.get("ZOTERO_LIBRARY_TYPE")
        # No environment fallback for collection - only use collection_name

        self.url = url
        self.pdf_path = pdf_path
        self.wait = wait
        self.storage_dir = Path(storage_dir)
        self.api_key = api_key
        self.library_id = library_id
        self.library_type = library_type
        self.collection = collection
        self.collection_name = collection_name or os.environ.get("ZOTERO_COLLECTION_NAME")
        self.verbose = verbose
        self.use_snapshot = use_snapshot

        # Extract domain from URL for file naming or use filename for PDF
        if self.url:
            parsed_url = urlparse(self.url)
            self.domain = parsed_url.netloc
            if self.domain.startswith("www."):
                self.domain = self.domain[4:]
        else:
            # Use the filename without extension as a fallback "domain"
            pdf_filename = os.path.basename(self.pdf_path)
            self.domain = os.path.splitext(pdf_filename)[0]
            # Ensure domain isn't overly long
            if len(self.domain) > 30:
                self.domain = self.domain[:30]

        # Configure logging
        configure_logger(
            log_level="DEBUG" if verbose else "INFO",
            console=True,
        )

        if verbose:
            logger.debug("Verbose logging enabled")

        # Zotero API configuration

        logger.info(f"Connecting to Zotero library: {self.library_id} ({self.library_type})")
        self.zot = zotero.Zotero(
            library_id,
            library_type,
            api_key,
        )

        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using storage directory: {self.storage_dir}")

        # Process based on what was provided
        if self.pdf_path:
            logger.info(f"Adding PDF {self.pdf_path} to Zotero...")
            parent_resp, attachment_resp = self.pdf_to_zotero()
            parent_key = extract_key(parent_resp)

            print(f"✓ Item created with key: {parent_key}")
        else:
            logger.info(f"Saving {self.url} to Zotero...")

            if self.use_snapshot:
                # Try to use Zotero's saveSnapshot API first
                self.save_url_with_snapshot()

                # Now also save the PDF as an attachment to this snapshot
                logger.info(f"Creating PDF attachment for snapshot")

                # Use a temporary directory to store the PDF before attaching
                pdf_dir = Path(self.storage_dir) / "ZoteroUploader"
                pdf_dir.mkdir(parents=True, exist_ok=True)

                # Create a temporary filename
                temp_filename = f"{self.domain}_{int(time.time())}.pdf"
                pdf_path = pdf_dir / temp_filename

                # Save the webpage as PDF
                title = save_webpage_as_pdf(self.url, str(pdf_path), self.wait)

                # Rename with better title
                sanitized_title = "".join(c for c in title if c.isalnum() or c in " ._-").strip()
                sanitized_title = sanitized_title[:50]  # Limit length
                new_filename = f"{sanitized_title}_{self.domain}.pdf"
                new_pdf_path = pdf_dir / new_filename
                pdf_path.rename(new_pdf_path)

                # When saving the snapshot the response
                # doesn't include the item key, so we need to find it
                # by searching for recently added items with this URL
                parent_key = self.find_item_by_url(self.url)
                logger.info(f"Found snapshot with key: {parent_key}")

                # Attach the PDF to the snapshot item
                logger.info(f"Attaching PDF to snapshot item: {parent_key}")
                shutil.copy2(str(new_pdf_path), str(Path.cwd() / new_pdf_path.name))

                # first: create the item
                attachment_template = self.zot.item_template('attachment', 'imported_file')
                attachment_template['title'] = f"{title} (PDF)"
                attachment_template['contentType'] = 'application/pdf'
                attachment_template['filename'] = new_pdf_path.name
                attachment_template['url'] = self.url
                attachment_template['parentItem'] = parent_key
                digest = hashlib.md5()  # noqa: S324
                with new_pdf_path.open("rb") as att:
                    for chunk in iter(lambda: att.read(8192), b""):
                        digest.update(chunk)
                attachment_template["md5"] = digest.hexdigest()

                attachment_resp = self.zot.create_items([attachment_template])
                logger.debug(f"Create_items response: {attachment_resp}")

                # # this upload method only works if not using webdav!
                # # Use the create_items endpoint with the file path
                # attachment_resp = self.zot.upload_attachments(
                #     attachments=[attachment_template],
                #     parentid=parent_key,
                #     basedir=new_pdf_path.absolute().parent,
                # )
                # logger.debug(f"Upload_attachments response: {attachment_resp}")

                # extract the key and move to storage
                attachment_key = extract_key(attachment_resp)
                self.move_pdf_to_zotero_storage(str(new_pdf_path), attachment_key, title)

                print(f"✓ Webpage item created with key: {parent_key} with PDF attachment")
            else:
                # Use the original PDF method
                parent_resp, attachment_resp = self.url_to_zotero()
                parent_key = extract_key(parent_resp)

                print(f"✓ Webpage item created with key: {parent_key}")

        # Add to collection if specified by name
        if self.collection_name:
            self.add_to_collection(parent_key)

        assert (
            "success" in attachment_resp and attachment_resp["success"]
        ) or ("unchanged" in attachment_resp and attachment_resp["unchanged"]), attachment_resp
        print(f"✓ PDF attachment added successfully")

        if self.url:
            print(f"\nURL: {self.url}")
        else:
            print(f"\nPDF: {self.pdf_path}")

        print("Item has been saved to your Zotero library.")
        logger.info("Successfully added to Zotero!")

    def add_to_zotero(
        self,
        pdf_path: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict, Dict]:
        """
        Add a webpage or PDF as an item with PDF attachment to Zotero.
        Called by both url_to_zotero and pdf_to_zotero.

        Args:
            pdf_path: Path to the PDF file to upload
            title: Title of the item (optional)
            metadata: Additional metadata to add (optional)

        Returns:
            Tuple containing (parent item response, attachment response)
        """

        # Choose the appropriate template based on whether we have a URL
        if self.url:
            # Create a webpage item for URLs
            parent_item = self.zot.item_template("webpage")
            logger.debug(f"Valid fields for webpage: {list(parent_item.keys())}")
            parent_item["url"] = self.url
            if title:
                parent_item["title"] = title
            parent_item["accessDate"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            # Create a document item for standalone PDFs
            parent_item = self.zot.item_template("document")
            logger.debug(f"Valid fields for document: {list(parent_item.keys())}")
            if title:
                parent_item["title"] = title

        # Add additional metadata if available
        if metadata:
            if "description" in metadata:
                parent_item["abstractNote"] = metadata["description"]

            if self.url and "domain" in metadata:
                parent_item["websiteTitle"] = metadata["domain"]

            if "author" in metadata:
                # Add author if available
                if parent_item["creators"][0]["creatorType"] == "author":
                    # Try to split name into first/last
                    name_parts = metadata["author"].split()
                    if len(name_parts) > 1:
                        parent_item["creators"][0]["lastName"] = name_parts[-1]
                        parent_item["creators"][0]["firstName"] = " ".join(
                            name_parts[:-1]
                        )
                    else:
                        parent_item["creators"][0]["lastName"] = metadata["author"]

        # Create the parent item in Zotero
        logger.info("Creating parent item in Zotero")
        try:
            creation_response = self.zot.create_items([parent_item])
        except Exception as e:
            logger.error(f"Error creating Zotero item: {str(e)}")
            logger.debug(
                f"Item data that caused error: {json.dumps(parent_item, indent=2)}"
            )
            raise

        if "success" not in creation_response or not creation_response["success"]:
            error_msg = f"Failed to create Zotero item: {creation_response}"
            logger.error(error_msg)
            raise Exception(error_msg)

        # Get the key of the created item, with better error handling
        if "success" not in creation_response or not creation_response["success"]:
            error_msg = f"Failed to create Zotero item: {creation_response}"
            logger.error(error_msg)
            raise Exception(error_msg)

        parent_key = extract_key(creation_response)
        logger.info(f"Created parent item with key: {parent_key}")

        # Get the PDF directory and filename using Path
        pdf_path_obj = Path(pdf_path).resolve()
        pdf_dir = str(pdf_path_obj.parent)
        pdf_filename = pdf_path_obj.name

        # Create a PDF attachment template for direct API upload
        attachment_template = self.zot.item_template("attachment", "imported_file")
        attachment_template["title"] = f"{title} (PDF)"
        attachment_template["contentType"] = "application/pdf"
        attachment_template["filename"] = pdf_filename
        attachment_template["url"] = ""  # Will be updated later

        # Start a local HTTP server in a thread to serve the PDF
        server_port = find_available_port(start_port=25852)
        server = SimpleHTTPServerThread(pdf_dir, server_port)
        server.start()

        attachment_response = {"success": {}, "failed": {}}

        try:
            local_url = f"http://localhost:{server_port}/{pdf_filename}"
            logger.info(f"Serving PDF at: {local_url}")

            # Ensure the PDF file exists and log its size
            if not pdf_path_obj.exists():
                error_msg = f"PDF file not found at {pdf_path_obj}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)

            logger.info(f"PDF size: {pdf_path_obj.stat().st_size} bytes")

            # # First try to use Zotero's registerAttachment API for better reliability
            # # Get proper path format for Zotero
            # abs_path = str(pdf_path_obj.resolve())
            # logger.info(f"Using absolute path for attachment: {abs_path}")
            #
            # # Create proper attachment item
            # attachment_template = self.zot.item_template('attachment', 'imported_file')
            # attachment_template['title'] = f"{title} (PDF)"
            # attachment_template['contentType'] = 'application/pdf'
            # attachment_template['filename'] = pdf_path_obj.name
            # attachment_template['url'] = self.url  # Set the original URL
            # attachment_template['parentItem'] = parent_key
            #
            # # Use the create_items endpoint with the file path
            # attachment_response = self.zot.upload_attachments(
            #     [attachment_template],
            #     Path(abs_path).relative_to(Path.cwd()),
            #     parent_key
            # )

            # Fallback to direct API upload
            logger.info("Using direct API upload")

            # Use attachment_simple as fallback
            try:
                attachment_response = self.zot.attachment_simple([pdf_path], parent_key)
                logger.debug(f"attachment_simple response: {attachment_response}")

                # Check if response is empty or has no success field
                if not attachment_response or "success" not in attachment_response:
                    logger.warning("Empty attachment response, trying alternate method")
                    # Try alternative approach: create attachment item and then update it
                    attachment_template = self.zot.item_template("attachment", "imported_file")
                    attachment_template["title"] = f"{title} (PDF)"
                    attachment_template["contentType"] = "application/pdf"
                    attachment_template["filename"] = pdf_filename
                    attachment_template["parentItem"] = parent_key

                    # First create the attachment item
                    created_item = self.zot.create_items([attachment_template])
                    logger.debug(f"Created attachment item: {created_item}")

                    # Then upload the file to that item
                    if "success" in created_item and created_item["success"]:
                        attachment_key = extract_key(created_item)
                        upload_response = self.zot.upload_attachment(attachment_key, pdf_path)
                        logger.debug(f"Upload attachment response: {upload_response}")
                        attachment_response = created_item  # Use the creation response
            except Exception as e:
                logger.error(f"Error using attachment_simple: {str(e)}")
                raise

            # After creating the attachment, get its key and move file to Zotero storage
            try:
                attachment_key = extract_key(attachment_response)
                logger.info(f"Created attachment with key: {attachment_key}")

                if not pdf_path_obj.exists():
                    logger.error(f"PDF file not found at: {pdf_path_obj}")
                    raise FileNotFoundError(f"PDF file not found: {pdf_path_obj}")

                # Move the file to Zotero storage if specified and we have a key
                logger.info(f"Moving PDF to Zotero storage: {self.storage_dir}")
                self.move_pdf_to_zotero_storage(
                    str(pdf_path_obj), attachment_key, title,
                )
            except Exception as e:
                logger.error(f"Error processing attachment: {e}")
                raise

            # Get the attachment
            attachment_item = self.zot.item(attachment_key)
            # Update its URL if we have one
            if self.url:
                attachment_item["data"]["url"] = self.url
                self.zot.update_item(attachment_item)

        finally:
            # Stop the HTTP server
            logger.info("Stopping local HTTP server")
            server.stop()

        return creation_response, attachment_response

    def url_to_zotero(
        self,
        storage_dir: str = None,
    ) -> Tuple[Dict, Dict]:
        """
        Process a URL and add it to Zotero with PDF attachment.

        Args:
            storage_dir: Path to directory where PDFs should be saved (optional)

        Returns:
            Tuple containing (parent item response, attachment response)
        """
        if not self.storage_dir:
            raise ValueError("self.storage_dir is required")

        # Use the specified storage directory with a ZoteroUploader subdirectory
        pdf_dir = Path(self.storage_dir) / "ZoteroUploader"
        pdf_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"PDF temporary storage directory: {pdf_dir}")

        # Create a temporary filename first (will rename after getting the title)
        temp_filename = f"{self.domain}_{int(time.time())}.pdf"
        pdf_path = pdf_dir / temp_filename

        # Save the webpage as PDF in a temporary location first
        logger.info(f"Processing URL: {self.url}")
        title = save_webpage_as_pdf(self.url, str(pdf_path), self.wait)

        # Rename the PDF with a more meaningful title but keep it in the temporary location
        sanitized_title = "".join(
            c for c in title if c.isalnum() or c in " ._-"
        ).strip()
        sanitized_title = sanitized_title[:50]  # Limit length
        new_filename = f"{sanitized_title}_{self.domain}.pdf"
        new_pdf_path = pdf_dir / new_filename

        # Rename the file
        pdf_path.rename(new_pdf_path)
        pdf_path = new_pdf_path
        logger.info(f"Temporarily saved PDF as: {pdf_path}")

        # Extract metadata using Playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(self.url, wait_until="networkidle", timeout=30000)
                metadata = get_webpage_metadata(page, self.url)
            finally:
                browser.close()

        # Add to Zotero
        logger.info(f"Adding to Zotero with storage directory: {self.storage_dir}")
        parent_resp, attach_resp = self.add_to_zotero(
            str(pdf_path),
            title,
            metadata,
        )

        # Log the responses for debugging
        logger.debug(f"Parent response: {parent_resp}")
        logger.debug(f"Attachment response: {attach_resp}")

        # If the attachment was successful, we'll organize the file properly
        assert "success" in attach_resp and attach_resp["success"], attach_resp
        # Extract the attachment key
        attachment_key = extract_key(attach_resp)

        # Create the proper Zotero storage directory structure
        zotero_subfolder = Path(self.storage_dir) / attachment_key
        zotero_subfolder.mkdir(exist_ok=True)

        # Move the PDF to its final location in Zotero storage
        final_pdf_path = zotero_subfolder / new_filename
        logger.info(f"Moving PDF to final Zotero storage location: {final_pdf_path}")

        if pdf_path.exists():
            shutil.copy2(str(pdf_path), str(final_pdf_path))

            # Create a .zotero-ft-cache file to indicate it's been indexed
            (zotero_subfolder / ".zotero-ft-cache").touch()

            # Remove the original temp file
            try:
                pdf_path.unlink()
                logger.info(f"Removed temporary PDF file: {pdf_path}")
            except Exception as e:
                logger.warning(f"Could not remove temporary PDF: {e}")

            print(f"✓ PDF moved to Zotero storage: {final_pdf_path}")

        # Return the responses
        return parent_resp, attach_resp

    def pdf_to_zotero(self) -> Tuple[Dict, Dict]:
        """
        Process a local PDF file and add it to Zotero.

        Returns:
            Tuple containing (parent item response, attachment response)
        """
        if not self.pdf_path:
            raise ValueError("PDF path is required")

        # Verify the PDF file exists and get absolute path
        pdf_path_obj = Path(self.pdf_path).resolve()
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

        logger.info(f"Processing PDF: {pdf_path_obj}")

        # Use the filename as the title if it's not obviously a temporary name
        filename = pdf_path_obj.name
        title = os.path.splitext(filename)[0]

        # Try to get a better title by examining the PDF metadata
        try:
            with open(pdf_path_obj, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                if pdf_reader.metadata and pdf_reader.metadata.title:
                    pdf_title = pdf_reader.metadata.title
                    # Only use if it's not empty or just whitespace
                    if pdf_title and pdf_title.strip():
                        title = pdf_title.strip()
                        logger.info(f"Extracted title from PDF metadata: {title}")
        except Exception as e:
            logger.warning(f"Could not extract PDF metadata: {e}")

        # Create simple metadata
        metadata = {
            "title": title,
            "domain": self.domain,
            "accessDate": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # Add to Zotero
        logger.info(f"Adding PDF to Zotero with title: {title}")
        parent_resp, attach_resp = self.add_to_zotero(
            str(pdf_path_obj),
            title,
            metadata,
        )

        return parent_resp, attach_resp

    def find_collection_by_name(self, name: str) -> Optional[str]:
        """
        Find a collection key by its name.

        Args:
            name: The name of the collection to find

        Returns:
            The collection key if found, None otherwise
        """
        try:
            logger.info(f"Searching for collection with name: {name}")
            collections = self.zot.collections()

            for collection in collections:
                if "data" in collection and "name" in collection["data"]:
                    if collection["data"]["name"] == name:
                        collection_key = collection["data"]["key"]
                        logger.info(f"Found collection '{name}' with key: {collection_key}")
                        return collection_key

            logger.warning(f"Could not find collection with name: {name}")
            return None
        except Exception as e:
            logger.error(f"Error finding collection by name: {e}")
            return None

    def add_to_collection(self, item_key: str) -> bool:
        """
        Add an item to the specified collection.

        Args:
            item_key: The key of the item to add to the collection

        Returns:
            True if successful, False otherwise
        """
        # If we have a collection key directly provided, use it
        collection_key = self.collection

        # If we have a collection name, try to find the key by name
        if not collection_key and self.collection_name:
            collection_key = self.find_collection_by_name(self.collection_name)
            if not collection_key:
                logger.warning(f"Could not find collection with name: {self.collection_name}")
                return False

        if not collection_key:
            logger.warning("No collection specified, skipping collection assignment")
            return False

        try:
            logger.info(f"Adding item {item_key} to collection {collection_key}")

            # Get the current item
            item = self.zot.item(item_key)

            # Update the item's collections
            if "data" in item and "collections" in item["data"]:
                # Make sure we're not adding a duplicate
                if collection_key not in item["data"]["collections"]:
                    item["data"]["collections"].append(collection_key)
                    # Update the item in Zotero
                    result = self.zot.update_item(item)
                else:
                    logger.info(f"Item already in collection {collection_key}")
                    return True
            else:
                logger.error("Invalid item data structure returned from Zotero API")
                return False

            logger.debug(f"Collection addition response: {result}")

            # Print appropriate message based on which collection identifier was used
            if self.collection_name and self.collection_name != collection_key:
                logger.info(f"Successfully added to collection: {self.collection_name} ({collection_key})")
                print(f"✓ Added to collection: {self.collection_name}")
            else:
                logger.info(f"Successfully added to collection: {collection_key}")
                print(f"✓ Added to collection: {collection_key}")

            return True
        except Exception as e:
            logger.error(f"Error adding to collection: {e}")
            return False


    def save_url_with_snapshot(self):
        """
        Save a URL using Zotero connector's saveSnapshot API.

        This method communicates directly with the running Zotero instance
        via its connector API to save a webpage as a snapshot.

        Returns:
            The parent item key if successful, None otherwise
        """
        if not self.url:
            logger.error("URL is required for saveSnapshot")
            return None

        # Define the connector endpoint
        connector_url = "http://127.0.0.1:23119/connector/saveSnapshot"

        # Prepare the payload
        payload = {
            "url": self.url,
            "title": None  # Will be auto-detected by Zotero
        }

        # Extract domain from URL for metadata
        parsed_url = urlparse(self.url)
        domain = parsed_url.netloc
        if domain.startswith("www."):
            domain = domain[4:]

        try:
            # Get the title using Playwright for better accuracy
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                try:
                    logger.info(f"Fetching page title for {self.url}")
                    page.goto(self.url, wait_until="networkidle", timeout=30000)
                    title = page.title()
                    if title:
                        payload["title"] = title

                    # Get more metadata
                    metadata = get_webpage_metadata(page, self.url)
                    if "title" in metadata and metadata["title"]:
                        payload["title"] = metadata["title"]

                finally:
                    browser.close()
        except Exception as e:
            logger.warning(f"Error getting page title with Playwright: {e}")
            # Continue without title, Zotero will attempt to detect it

        logger.info(f"Using saveSnapshot to save {self.url}")
        logger.debug(f"Snapshot payload: {payload}")

        try:
            # Make the request to the Zotero connector
            response = requests.post(
                connector_url,
                json=payload,
                timeout=30
            )

            if response.status_code in [200, 201]:
                logger.info(f"Snapshot saved successfully (status code: {response.status_code})")
                logger.debug(f"Snapshot response: {response.text}")

                # Parse the response
                snapshot_data = response.json()

        except RequestException as e:
            logger.error(f"Error connecting to Zotero: {e}")
            # This usually means Zotero is not running
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving snapshot: {e}")
            raise

    def find_item_by_url(self, url: str, max_attempts: int = 3, delay: float = 5.0) -> Optional[str]:
        """
        Find a recently added Zotero item by its URL.

        Args:
            url: The URL to search for
            max_attempts: Maximum number of attempts to find the item
            delay: Delay between attempts in seconds

        Returns:
            The item key if found, None otherwise
        """
        logger.info(f"Waiting {delay}s for the snapshot to be created...")
        time.sleep(delay)

        # Sometimes it takes a moment for the item to appear in the Zotero database
        for attempt in range(max_attempts):
            try:
                # Get recent items, sorted by date added (newest first)
                items = self.zot.items(sort="dateAdded", direction="desc", limit=10)
                # sort so that oldest items are first and latest are last
                items = sorted(items, key=lambda x: datetime.fromisoformat(x["data"]["dateModified"].replace("Z", "+00:00")))
                items = [item for item in items if "data" in item]
                items = [item for item in items if "url" in item["data"]]
                items = [item for item in items if item["data"]["url"] == url]
                # keep only the webpage instead of the attachment
                items = [item for item in items if item["data"]["itemType"] == "webpage"]

                # If we didn't find it, wait and try again
                if not items:
                    logger.info(f"Item not found, waiting {delay} seconds and retrying...")
                    time.sleep(delay)
                    continue

                return items[-1]["data"]["key"]

            except Exception as e:
                logger.error(f"Error searching for item by URL: {e}")
                break

        logger.warning(f"Could not find item with URL: {url} after {max_attempts} attempts")
        return None

    def move_pdf_to_zotero_storage(
        self, pdf_path: str, attachment_key: str, title: str,
    ) -> str:
        """
        Called by add_to_zotero
        Copy the PDF file to the Zotero storage location, preserving the original
        if it was directly uploaded (not from a webpage).

        Args:
            pdf_path: Path to the PDF file to move
            attachment_key: The Zotero attachment key
            title: Title for the file (used for a better filename)

        Returns:
            Path to the new PDF location in Zotero storage
        """
        # Create Path objects
        pdf_path_obj = Path(pdf_path)
        storage_dir_obj = Path(self.storage_dir)

        # Log detailed storage info for debugging
        logger.info(f"Moving PDF to storage directory: {self.storage_dir}")
        logger.info(f"Attachment key: {attachment_key}")
        logger.info(f"Storage directory exists: {storage_dir_obj.exists()}")

        # Ensure the file exists
        if not pdf_path_obj.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return pdf_path

        # Ensure storage directory exists
        if not storage_dir_obj.exists():
            logger.error(f"Storage directory does not exist: {self.storage_dir}")
            return pdf_path

        # Create a directory in Zotero storage using the attachment key
        # This is the critical part - the PDF must be in a subfolder named with the attachment key
        zotero_dir = storage_dir_obj / attachment_key
        zotero_dir.mkdir(exist_ok=True)

        # Keep the original filename instead of creating a custom one
        # This is essential for Zotero to properly recognize the file
        original_filename = pdf_path_obj.name
        zotero_pdf_path = zotero_dir / original_filename

        # Copy the PDF to Zotero storage
        try:
            import shutil

            logger.info(f"Moving PDF to Zotero storage: {zotero_pdf_path}")
            shutil.copy2(str(pdf_path_obj), str(zotero_pdf_path))

            # Add a Zotero .zotero-ft-cache file to indicate it's been indexed
            # This helps Zotero recognize the file is ready for full-text indexing
            (zotero_dir / ".zotero-ft-cache").touch()

            # Only remove the original file if this is a URL-sourced PDF (not directly uploaded PDF)
            if self.url:
                try:
                    pdf_path_obj.unlink()
                    logger.info(f"Removed original PDF file: {pdf_path}")
                except Exception as e:
                    logger.warning(f"Could not remove original PDF: {e}")
            else:
                logger.info(f"Original PDF file preserved: {pdf_path}")

            print(f"✓ PDF copied to Zotero storage: {zotero_pdf_path}")
            return str(zotero_pdf_path)
        except Exception as e:
            logger.error(f"Error moving PDF to Zotero storage: {e}")
            return pdf_path


if __name__ == "__main__":
    fire.Fire(ZoteroUploader)
