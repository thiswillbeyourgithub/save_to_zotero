"""
Script to save webpages as PDFs and add them to Zotero.
Uses playwright for PDF generation and pyzotero for Zotero integration.
"""

import json
import os
import tempfile
import subprocess
import time
from datetime import datetime
from typing import Dict, Optional, Tuple, Any, Union, List
import requests
import fire
from pyzotero import zotero
from playwright.sync_api import sync_playwright
from pathlib import Path
from urllib.parse import urlparse
import io
import PyPDF2
from loguru import logger
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
        self.storage_dir = storage_dir
        self.api_key = api_key
        self.library_id = library_id
        self.library_type = library_type
        self.collection = collection
        self.collection_name = collection_name or os.environ.get("ZOTERO_COLLECTION_NAME")
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

        logger.info(f"Connecting to Zotero library: {self.library_id} ({self.library_type})")
        self.zot = zotero.Zotero(
            library_id,
            library_type,
            api_key,
        )

        # Ensure storage directory exists
        os.makedirs(storage_dir, exist_ok=True)
        logger.info(f"Using storage directory: {storage_dir}")

        # Process based on what was provided
        if self.pdf_path:
            logger.info(f"Adding PDF {self.pdf_path} to Zotero...")
            parent_resp, attachment_resp = self.pdf_to_zotero()
            parent_key = extract_key(parent_resp)
            
            # Add to collection if specified by name
            if self.collection_name:
                self.add_to_collection(parent_key)
                
            print(f"✓ Item created with key: {parent_key}")
            
            # Create snapshot if URL was provided and link to parent
            if self.url:
                self.create_zotero_snapshot(self.url, title=os.path.basename(self.pdf_path), parent_key=parent_key)
        else:
            logger.info(f"Saving {self.url} to Zotero...")
            # Store the title returned from url_to_zotero so we can use it for the snapshot
            parent_resp, attachment_resp, webpage_title = self.url_to_zotero()
            parent_key = extract_key(parent_resp)
            
            # Add to collection if specified by name
            if self.collection_name:
                self.add_to_collection(parent_key)
                
            print(f"✓ Webpage item created with key: {parent_key}")
            
            # Create snapshot through Zotero connector and link to parent
            self.create_zotero_snapshot(self.url, title=webpage_title, parent_key=parent_key)

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
            # breakpoint()
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
                logger.error(f"Attachment response: {attachment_response}")
                # If we can find the key in the "unchanged" list, we can still proceed
                if ("unchanged" in attachment_response and 
                    isinstance(attachment_response["unchanged"], list) and 
                    len(attachment_response["unchanged"]) > 0 and
                    "key" in attachment_response["unchanged"][0]):
                    
                    attachment_key = attachment_response["unchanged"][0]["key"]
                    logger.info(f"Using unchanged attachment key: {attachment_key}")
                    
                    # Move the file to Zotero storage
                    self.move_pdf_to_zotero_storage(
                        str(pdf_path_obj), attachment_key, title,
                    )
                else:
                    # Re-raise the exception if we couldn't recover
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
    ) -> Tuple[Dict, Dict, str]:
        """
        Process a URL and add it to Zotero with PDF attachment.

        Args:
            storage_dir: Path to directory where PDFs should be saved (optional)

        Returns:
            Tuple containing (parent item response, attachment response, webpage title)
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
            import shutil

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

        # Return the responses and title
        return parent_resp, attach_resp, title

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
            
    def create_zotero_snapshot(self, url: str, title: Optional[str] = None, parent_key: Optional[str] = None) -> bool:
        """
        Create a Zotero snapshot of a webpage using the Zotero Connector API.
        This is called after the PDF is added to provide an HTML snapshot in addition to the PDF.
        
        Args:
            url: The URL of the webpage to snapshot
            title: The title of the webpage (optional)
            parent_key: The Zotero parent item key to attach the snapshot to (optional)
            
        Returns:
            True if successful, False otherwise
        """
        # Skip if no URL provided
        if not url:
            logger.debug("No URL provided, skipping snapshot creation")
            return False
            
        # Try to connect to the Zotero Connector
        connector_url = "http://127.0.0.1:23119/connector/saveSnapshot"
        
        # Prepare the request payload
        payload = {
            "url": url,
        }
        
        # Add title if provided
        if title:
            payload["title"] = title
            
        try:
            logger.info(f"Creating Zotero snapshot for URL: {url}")
            response = requests.post(
                connector_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=5  # Short timeout, we don't want to block for too long
            )
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                logger.info(f"Zotero snapshot created successfully: {response_data}")
                print(f"✓ Web snapshot created via Zotero Connector")
                
                # If parent_key is provided, find the snapshot and set its parent
                if parent_key:
                    # Wait a moment for Zotero to process the snapshot
                    time.sleep(1)
                    self.link_snapshot_to_parent(url, parent_key)
                    
                return True
            else:
                logger.warning(f"Failed to create Zotero snapshot: HTTP {response.status_code}")
                logger.debug(f"Response: {response.text}")
                print("⚠️ Could not create web snapshot via Zotero Connector (is Zotero running?)")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.warning("Could not connect to Zotero Connector. Is Zotero running?")
            print("⚠️ Could not connect to Zotero Connector (is Zotero running?)")
            return False
        except Exception as e:
            logger.warning(f"Error creating Zotero snapshot: {e}")
            print("⚠️ Failed to create web snapshot via Zotero Connector")
            return False
    
    def link_snapshot_to_parent(self, url: str, parent_key: str, max_attempts: int = 5) -> bool:
        """
        Find a recently created snapshot and link it to the specified parent item.
        
        Args:
            url: The URL of the snapshot to find
            parent_key: The parent item key to link the snapshot to
            max_attempts: Maximum number of attempts to find the snapshot
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Searching for snapshot with URL: {url}")
        logger.info(f"To link to parent with key: {parent_key}")
        
        # Make multiple attempts as the snapshot might not be immediately available
        for attempt in range(max_attempts):
            try:
                # Get recent items - increase limit to improve chances of finding it
                items = self.zot.items(limit=50, sort="dateAdded", direction="desc")
                
                # Look for a snapshot matching our URL
                snapshots_found = 0
                for item in items:
                    item_data = item.get("data", {})
                    item_url = item_data.get("url", "")
                    item_type = item_data.get("itemType", "")
                    
                    # For debugging - count how many snapshots we're finding
                    if item_type in ["webpage", "attachment"] and item_url == url:
                        snapshots_found += 1
                        logger.debug(f"Found snapshot match #{snapshots_found}: key={item_data.get('key')}, hasParent={'parentItem' in item_data}")
                    
                    # Check if this is a snapshot matching our URL
                    if (item_type in ["webpage", "attachment"] and 
                        item_url == url and 
                        "parentItem" not in item_data):  # Not already a child
                        
                        # This is likely our snapshot, set its parent
                        item_key = item_data.get("key")
                        logger.info(f"Found snapshot with key: {item_key}")
                        
                        # Set the parent item
                        item_data["parentItem"] = parent_key
                        
                        # Update the item
                        update_response = self.zot.update_item(item)
                        logger.debug(f"Update response: {update_response}")
                        logger.info(f"Successfully linked snapshot to parent: {parent_key}")
                        print(f"✓ Linked web snapshot to parent item")
                        return True
                
                # Log how many snapshots we found in this attempt
                logger.debug(f"Attempt {attempt+1}: Found {snapshots_found} snapshots matching URL, none without parents")
                
                # If not found, wait before trying again
                if attempt < max_attempts - 1:
                    # Increase wait time with each attempt
                    wait_time = 2 + attempt  # 2, 3, 4, 5, 6 seconds
                    logger.info(f"Snapshot without parent not found, waiting {wait_time}s before retry (attempt {attempt+1}/{max_attempts})")
                    time.sleep(wait_time)
            
            except Exception as e:
                logger.error(f"Error linking snapshot to parent: {e}")
                # Log more detailed error info
                import traceback
                logger.debug(f"Error details: {traceback.format_exc()}")
                
                # Still try the remaining attempts
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                return False
        
        # If we get here, we've exhausted all attempts
        logger.warning(f"Could not find snapshot without parent after {max_attempts} attempts")
        print("⚠️ Note: Web snapshot was created but couldn't be linked to the parent item")
        return False


if __name__ == "__main__":
    fire.Fire(ZoteroUploader)
