"""
Script to save webpages as PDFs and add them to Zotero.
Uses playwright for PDF generation and pyzotero for Zotero integration.
"""
import json
import os
import tempfile
import time
from datetime import datetime
from typing import Dict, Optional, Tuple
import requests
import shutil
from pyzotero import zotero
from playwright.sync_api import sync_playwright
from pathlib import Path
from urllib.parse import urlparse
from loguru import logger
from requests.exceptions import RequestException
from .utils.misc import (
    find_available_port,
    configure_logger,
    ensure_zotero_running,
)
from .utils.webpage import (
    save_webpage_as_pdf,
    get_webpage_metadata,
    SimpleHTTPServerThread,
)

# Configure module logger
configure_logger(__name__)

DEFAULT_CONNECTOR_HOST = "http://127.0.0.1"
DEFAULT_CONNECTOR_PORT = 23119


class SaveToZotero:
    """
    Class for uploading webpages to Zotero as PDF attachments.
    """

    VERSION: str = "1.1.2"

    def __init__(
        self,
        url: Optional[str] = None,
        pdf_path: Optional[str] = None,
        wait: int = 5000,
        api_key: Optional[str] = None,
        library_id: Optional[str] = None,
        library_type: str = "user",
        collection: Optional[str] = None,
        collection_name: Optional[str] = None,
        connector_host: Optional[str] = None,
        connector_port: Optional[int] = None,
        tags: str = "save_to_zotero",
        verbose: bool = False,
    ):
        """
        Save a webpage as PDF and add it to Zotero, or add an existing PDF file.

        Args:
            url: The URL of the webpage to save (optional if pdf_path is provided)
            pdf_path: Path to an existing PDF file to add (optional if url is provided)
            wait: Time to wait (ms) for the page to fully load (for URLs)
            api_key: Zotero API key (defaults to ZOTERO_API_KEY environment variable if not provided)
            library_id: Zotero library ID (defaults to ZOTERO_LIBRARY_ID environment variable if not provided)
            library_type: Zotero library type (must be "user" or "group", defaults to ZOTERO_LIBRARY_TYPE if set)
            collection: Collection key to add the item to (defaults to ZOTERO_COLLECTION environment variable if not provided)
            collection_name: Collection name to add the item to (will search for a collection with this name)
            connector_host: Zotero connector host (defaults to ZOTERO_CONNECTOR_HOST environment variable or http://127.0.0.1)
            connector_port: Zotero connector port (defaults to ZOTERO_CONNECTOR_PORT environment variable or 23119)
            tags: Comma-separated list of tags to add to the item (defaults to "save_to_zotero")
            verbose: Enable verbose logging

        """
        if not url and not pdf_path:
            raise ValueError("Either url or pdf_path must be provided")

        assert not (pdf_path and url), "Must supply a url or a pdf but not both"

        # Connector host/port config with env var fallbacks
        self.connector_host = connector_host or os.environ.get(
            "ZOTERO_CONNECTOR_HOST", DEFAULT_CONNECTOR_HOST
        )
        self.connector_port = connector_port or int(
            os.environ.get("ZOTERO_CONNECTOR_PORT", DEFAULT_CONNECTOR_PORT)
        )

        # Make sure Zotero is running
        ensure_zotero_running(self.connector_host, self.connector_port)

        api_key = api_key or os.environ.get("ZOTERO_API_KEY")
        library_id = library_id or os.environ.get("ZOTERO_LIBRARY_ID")
        library_type = library_type or os.environ.get("ZOTERO_LIBRARY_TYPE")
        # No environment fallback for collection - only use collection_name

        self.url = url
        self.pdf_path = Path(pdf_path) if pdf_path else None
        self.wait = wait
        # Create a temporary directory instead of using a fixed storage dir
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.temp_dir.name)
        self.api_key = api_key
        self.library_id = library_id
        self.library_type = library_type
        self.collection = collection
        self.collection_name = collection_name or os.environ.get(
            "ZOTERO_COLLECTION_NAME"
        )
        self.tags = tags.split(",") if tags else []
        self.verbose = verbose

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

        logger.info(
            f"Connecting to Zotero library: {self.library_id} ({self.library_type})"
        )
        self.zot = zotero.Zotero(
            library_id,
            library_type,
            api_key,
        )

        # Temporary directory already exists, so we just log it
        logger.info(f"Using temporary storage directory: {self.storage_dir}")

        # Process based on what was provided
        if self.pdf_path:
            logger.info(f"Adding PDF {self.pdf_path} to Zotero...")
            attachment_item, _ = self.save_pdf_using_snapshot()
            # unfortunately the metadata cannot be stored in the extra field
            # for an attachment as they do not accept an extra field

            # Remove the url as localhost was just for uploading the pdf
            local_url = attachment_item["data"]["url"]
            del attachment_item["data"]["url"]
            attachment_item["data"]["filename"] = self.pdf_path.name
            update_resp = self.zot.update_item(attachment_item)
            logger.debug(f"Update item response: {update_resp}")

            attachment_key = attachment_item["data"]["key"]

            print(f"✓ Item for PDF created with key: {attachment_key}")

            # Add tags if specified
            if self.tags:
                self.add_tags_to_item(attachment_key)

            # Add to collection if specified by name
            if self.collection_name:
                self.add_to_collection(attachment_key)

            print("✓ PDF attachment added successfully")
        elif self.url:
            logger.info(f"Saving {self.url} to Zotero...")

            logger.info("Saving url using the connector API")
            webpage_key = self.save_url_using_snapshot()
            logger.info(f"Snapshot was created with key: {webpage_key}")

            # Now also save the PDF as an attachment to this snapshot
            logger.info("Now let's create a PDF attachment for snapshot")
            attachment_item, metadata = self.save_pdf_using_snapshot()

            # update the meta field of the webpage to contain metadata
            logger.info("Updating metadata of webpage")
            time.sleep(1)
            webpage = self.zot.item(webpage_key)
            metadata["save_to_zotero_version"] = self.VERSION
            webpage["data"]["extra"] = "\n".join(
                [
                    f"{k}: {v}"
                    for k, v in metadata.items()
                ]
            )
            metadata_update = self.zot.update_item(webpage)
            logger.debug(f"Metadata update answer: {metadata_update}")

            assert metadata_update, (
                        "Error when updating metadata of webpage "
                        f"to '{webpage['data']['extra']}'")

            # Update its URL to not be localhost
            logger.info("Waiting 10s for item to be available for update...")
            time.sleep(10)
            local_url = attachment_item["data"]["url"]
            attachment_item["data"]["url"] = self.url
            attachment_item["data"]["parentItem"] = webpage_key
            attachment_item["data"]["filename"] = metadata["title"] + ".pdf"
            update_resp = self.zot.update_item(attachment_item)
            logger.debug(f"Update item response: {update_resp}")

            # now that we updated and moved the attachment we can delete
            # the now empty item with url localhost
            logger.info("Waiting 10s for attachment update to be processed...")
            time.sleep(10)
            empty = self.zot.item(self.find_item_by_url(local_url, itemType="webpage"))
            if empty["meta"]["numChildren"] == 0:
                self.zot.delete_item(empty)

            print(f"✓ Webpage item created with key: {webpage_key} with PDF attachment")

            # Add tags if specified and wait for system to be ready
            logger.info("Waiting 10s before adding tags and collection...")
            time.sleep(10)

            if self.tags:
                self.add_tags_to_item(webpage_key)

            # Add to collection if specified by name
            if self.collection_name:
                self.add_to_collection(webpage_key)
        else:
            raise Exception()

        print("Item has been saved to your Zotero library.")
        logger.info("Successfully added to Zotero!")

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
                        logger.info(
                            f"Found collection '{name}' with key: {collection_key}"
                        )
                        return collection_key

            logger.warning(f"Could not find collection with name: {name}")
            return None
        except Exception as e:
            logger.error(f"Error finding collection by name: {e}")
            return None

    def add_tags_to_item(self, item_key: str) -> bool:
        """
        Add tags to an item.

        Args:
            item_key: The key of the item to add tags to

        Returns:
            True if successful, False otherwise
        """
        if not self.tags:
            logger.info("No tags specified, skipping tag assignment")
            return False

        try:
            logger.info(f"Adding tags {self.tags} to item {item_key}")

            # Get the current item
            item = self.zot.item(item_key)

            # Update the item's tags
            if "data" in item and "tags" in item["data"]:
                # Add each tag to the item
                for tag in self.tags:
                    tag = tag.strip()
                    if tag:  # Skip empty tags
                        # Tag format for Zotero API
                        tag_obj = {"tag": tag}
                        # Check if the tag already exists
                        if not any(t.get("tag") == tag for t in item["data"]["tags"]):
                            item["data"]["tags"].append(tag_obj)

                # Update the item in Zotero
                result = self.zot.update_item(item)
                logger.debug(f"Tag addition response: {result}")
                logger.info(f"Successfully added tags: {', '.join(self.tags)}")
                print(f"✓ Added tags: {', '.join(self.tags)}")
                return True
            else:
                logger.error("Invalid item data structure returned from Zotero API")
                return False

        except Exception as e:
            logger.error(f"Error adding tags: {e}")
            return False

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
                logger.warning(
                    f"Could not find collection with name: {self.collection_name}"
                )
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
                logger.info(
                    f"Successfully added to collection: {self.collection_name} ({collection_key})"
                )
                print(f"✓ Added to collection: {self.collection_name}")
            else:
                logger.info(f"Successfully added to collection: {collection_key}")
                print(f"✓ Added to collection: {collection_key}")

            return True
        except Exception as e:
            logger.error(f"Error adding to collection: {e}")
            return False

    def save_url_using_snapshot(self) -> Optional[str]:
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
        connector_url = (
            f"{self.connector_host}:{self.connector_port}/connector/saveSnapshot"
        )

        # Prepare the payload
        payload = {"url": self.url, "title": None}  # Will be auto-detected by Zotero

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
            response = requests.post(connector_url, json=payload, timeout=30)

            assert response.status_code in [200, 201], response.status_code
            logger.info(
                f"Snapshot saved successfully (status code: {response.status_code})"
            )
            logger.debug(f"Snapshot response: {response.text}")

            # When saving the snapshot the response
            # doesn't include the item key, so we need to find it
            # by searching for recently added items with this URL
            snapshot_data = self.find_item_by_url(self.url, itemType="webpage")

            return snapshot_data

        except RequestException as e:
            logger.error(f"Error connecting to Zotero: {e}")
            # This usually means Zotero is not running
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving snapshot: {e}")
            raise

    def save_pdf_using_snapshot(self) -> Tuple[Dict, Dict]:
        """
        Save a pdf file using Zotero connector's saveSnapshot API.

        This method communicates directly with the running Zotero instance
        via its connector API to save a local pdf using the connector API.

        Returns:
            The attachment item data if successful
        """
        # Use a temporary directory to store the PDF before attaching
        pdf_dir = Path(self.storage_dir) / "SaveToZotero"
        pdf_dir.mkdir(parents=True, exist_ok=True)

        # Create a temporary filename
        temp_filename = f"{self.domain}_{int(time.time())}.pdf"
        pdf_path = pdf_dir / temp_filename

        if self.url:
            # Save the webpage as PDF
            metadata = save_webpage_as_pdf(self.url, str(pdf_path), self.wait)
            # Rename with better title
            title = metadata["title"]
            sanitized_title = "".join(
                c for c in title if c.isalnum() or c in " ._-"
            ).strip()
            sanitized_title = sanitized_title[:50]  # Limit length
            new_filename = f"{sanitized_title}_{self.domain}.pdf"
            new_pdf_path = pdf_dir / new_filename
            pdf_path.rename(new_pdf_path)
        else:
            title = self.pdf_path.stem
            new_pdf_path = pdf_dir / self.pdf_path.name
            new_pdf_path.unlink(missing_ok=True)
            shutil.copy2(str(self.pdf_path), str(pdf_dir / self.pdf_path.name))

        # Attach the PDF to the webpage item
        logger.info("Attaching PDF to the webpage item")

        # Start a local HTTP server in a thread to serve the PDF
        logger.info("Starting the local http server to serve the PDF")
        server_port = find_available_port(start_port=25852)
        server = SimpleHTTPServerThread(pdf_dir, server_port)
        server.start()

        try:
            # copy the pdf to a new file with predictable name to
            # avoid issues like space in filenames that might
            # break the url
            shutil.copy2(
                str(new_pdf_path), str(new_pdf_path.parent / "during_transfer.pdf")
            )
            local_url = f"http://localhost:{server_port}/during_transfer.pdf"
            logger.info(f"Serving PDF at: {local_url}")

            # asking the connector api to save the pdf
            connector_url = (
                f"{self.connector_host}:{self.connector_port}/connector/saveSnapshot"
            )
            payload = {
                "url": local_url,
                "title": title,
                "filename": new_pdf_path.name,
                "contentType": "application/pdf",
                "itemType": "attachment",
            }
            headers = {"Content-Type": "application/json"}
            response = requests.post(
                connector_url, headers=headers, data=json.dumps(payload)
            )
            logger.debug(f"saveSnapshot response: {response.text}")

        finally:
            # Stop the HTTP server
            logger.info("Stopping local HTTP server")
            server.stop()
            (new_pdf_path.parent / "during_transfer.pdf").unlink()

        # Get the attachment item of that new pdf
        attachment_key = self.find_item_by_url(local_url, itemType="attachment")
        attachment_item = self.zot.item(attachment_key)

        return attachment_item, metadata

    def find_item_by_url(
        self,
        url: str,
        max_attempts: int = 3,
        delay: float = 30.0,
        itemType: str = "webpage",
    ) -> Optional[str]:
        """
        Find a recently added Zotero item by its URL.

        Args:
            url: The URL to search for
            max_attempts: Maximum number of attempts to find the item
            delay: Delay between attempts in seconds
            itemType: The type of item to search for (e.g., 'webpage' or 'attachment')

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
                items = sorted(
                    items,
                    key=lambda x: datetime.fromisoformat(
                        x["data"]["dateModified"].replace("Z", "+00:00")
                    ),
                )
                items = [item for item in items if "data" in item]
                items = [item for item in items if "url" in item["data"]]
                items = [item for item in items if item["data"]["url"] == url]
                # keep only the webpage instead of the attachment etc
                if itemType:
                    items = [
                        item for item in items if item["data"]["itemType"] == itemType
                    ]

                # If we didn't find it, wait and try again
                if not items:
                    logger.info(
                        f"Item not found, waiting {delay} seconds and retrying..."
                    )
                    time.sleep(delay)
                    continue

                logger.debug(f"Items corresponding to URL {url}:")
                for item in items:
                    logger.debug(item)

                return items[-1]["data"]["key"]

            except Exception as e:
                logger.error(f"Error searching for item by URL: {e}")
                break

        logger.warning(
            f"Could not find item with URL: {url} after {max_attempts} attempts"
        )
        return None
