"""
Utility functions for web page processing and operations.
"""

import os
import threading
import http.server
import socketserver
import random
import time
from datetime import datetime
from typing import Dict, Any
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Page

from .misc import configure_logger

# Configure module logger
logger = configure_logger(__name__)


def save_webpage_as_pdf(url: str, output_path: str, wait_for_load: int = 5000) -> dict:
    """
    Save a webpage as a PDF using Playwright with human-like behavior.

    Args:
        url: The URL of the webpage to save
        output_path: The path where the PDF will be saved
        wait_for_load: Base time to wait in ms for page to fully load (will be randomized)

    Returns:
        The metadata of the page
    """
    # Default user agent that will be used if environment variable is not set
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

    # Common desktop user agents for random selection
    user_agents = [
        DEFAULT_USER_AGENT,
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    ]

    # Get user agent from environment variable or choose randomly
    user_agent = os.environ.get("ZOTERO_USER_AGENT", random.choice(user_agents))

    viewport = {"width": 1280, "height": 900}  # Standard readable size
    device_scale_factor = 1.5  # Good balance for text clarity
    java_script_enabled = True
    locale = "en-US"
    timezone_id = "America/New_York"

    with sync_playwright() as p:
        # Configure browser with custom user agent and other options
        launch_args = {
            "args": ["--disable-blink-features=AutomationControlled"]
        }
        
        # Check if user data directory is specified in environment variable
        user_data_dir = os.environ.get("ZOTERO_BROWSER_USER_DATA_DIR")
        
        if user_data_dir:
            logger.info(f"Using browser user data directory: {user_data_dir}")
            logger.info("Running browser in visible mode with user data directory")
            
            # Use launch_persistent_context for user data directories
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,  # Always visible when using user data dir
                args=["--disable-blink-features=AutomationControlled"],
                user_agent=user_agent,
                viewport=viewport,
                device_scale_factor=device_scale_factor,
                java_script_enabled=java_script_enabled,
                locale=locale,
                timezone_id=timezone_id,
            )
            browser = None  # No separate browser instance in this case
        else:
            # Default to headless mode when no user data directory is specified
            launch_args["headless"] = True
            browser = p.chromium.launch(**launch_args)
            
            # Create context with optimal reading settings for all devices
            context = browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                device_scale_factor=device_scale_factor,
                java_script_enabled=java_script_enabled,
                locale=locale,
                timezone_id=timezone_id,
            )

        # Add humanizing attributes to prevent fingerprinting
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
        """
        )

        page = context.new_page()

        try:
            # Add small random delay before navigation (100-500ms)
            time.sleep(random.randint(100, 500) / 1000)

            logger.info(f"Navigating to {url}")
            # Navigate to the URL with a timeout
            page.goto(url, wait_until="networkidle", timeout=45000)

            # Use consistent wait time
            page.wait_for_timeout(wait_for_load)

            # Simulate human-like scrolling behavior
            _simulate_scrolling(page)

            # Expand dropdowns, accordions, and other hidden content
            _expand_hidden_elements(page)

            # Small consistent delay before getting title
            time.sleep(100 / 1000)

            # Extract metadata for later use
            metadata = get_webpage_metadata(page, url)

            # add more metadata
            metadata["user_agent"] = user_agent
            metadata["viewport"] = viewport
            metadata["device_scale_factor"] = device_scale_factor
            metadata["java_script_enabled"] = java_script_enabled
            metadata["locale"] = locale
            metadata["timezone_id"] = timezone_id

            # Get the page title for metadata
            title = metadata["title"]
            logger.info(f"Retrieved page title: {title}")

            # Configure PDF options for better quality
            page.emulate_media(media="screen")
            logger.info(f"Generating PDF at {output_path}")

            # Consistent delay before PDF generation
            time.sleep(300 / 1000)

            page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                scale=0.9,  # Slightly scaled down to fit more content
                margin={
                    "top": "0.4in",
                    "bottom": "0.4in",
                    "left": "0.4in",
                    "right": "0.4in",
                },
            )

            context.close()
            if browser:  # Only close browser if it was created separately
                browser.close()
            return metadata
        except Exception as e:
            logger.error(f"Error saving webpage as PDF: {str(e)}")
            context.close()
            if browser:  # Only close browser if it was created separately
                browser.close()
            raise e


def _simulate_scrolling(page: Page) -> None:
    """
    Simulate human-like scrolling behavior on a webpage.

    Args:
        page: The Playwright page object
    """
    try:
        # Get page height
        height = page.evaluate("document.body.scrollHeight")

        # Use a systematic approach to scroll the entire page
        viewport_height = page.viewport_size["height"]

        # Calculate number of scrolls needed to cover the entire page
        num_scrolls = max(3, int(height / viewport_height) + 1)

        for i in range(num_scrolls):
            # Scroll to specific positions to ensure complete page coverage
            scroll_to = min(
                i * (viewport_height * 0.8), height
            )  # 80% overlap for better content capture

            # Execute the scroll with smooth behavior
            page.evaluate(f"window.scrollTo({{top: {scroll_to}, behavior: 'smooth'}})")

            # Consistent pause between scrolls
            page.wait_for_timeout(800)

    except Exception as e:
        logger.warning(f"Error during scrolling simulation: {str(e)}")
        # Continue if scrolling fails - this is non-critical


def _expand_hidden_elements(page: Page) -> None:
    """
    Expand dropdowns, accordions, and other hidden content to ensure
    all text is visible in the PDF.

    Args:
        page: The Playwright page object
    """
    try:
        # Consistent small delay before expanding elements
        time.sleep(200 / 1000)

        # Execute JavaScript to expand common interactive elements
        page.evaluate(
            """() => {
            // Function to expand elements
            const expandElements = () => {
                // 1. Click on common dropdown/accordion triggers
                const clickSelectors = [
                    // Common accordion/dropdown triggers
                    'details:not([open])',
                    '.accordion:not(.active), .accordion:not(.show)',
                    '.collapse-trigger, .expand-trigger',
                    '[aria-expanded="false"]',
                    '.dropdown-toggle, .dropdown-trigger',
                    // Read more buttons
                    '.read-more, .show-more',
                    // FAQ elements
                    '.faq-question:not(.active), .faq-item:not(.active)',
                    // Tab panels that might be hidden
                    '.tab:not(.active)'
                ];
                
                // Process each type of clickable element
                clickSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        try {
                            el.click();
                        } catch (e) {
                            // Ignore errors if element can't be clicked
                        }
                    });
                });
                
                // 2. Force-expand elements by setting attributes and styles
                // Force open details elements
                document.querySelectorAll('details').forEach(el => {
                    el.setAttribute('open', 'true');
                });
                
                // Show collapsed/hidden elements
                const showSelectors = [
                    '.collapse:not(.show)',
                    '.accordion-content', 
                    '.dropdown-menu',
                    '.hidden-content',
                    '[aria-hidden="true"]'
                ];
                
                showSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        // Set multiple display-related properties to ensure visibility
                        el.style.display = 'block';
                        el.style.visibility = 'visible';
                        el.style.opacity = '1';
                        el.style.height = 'auto';
                        el.style.overflow = 'visible';
                        el.setAttribute('aria-hidden', 'false');
                        
                        // Add active/show classes that might be used for showing content
                        el.classList.add('active');
                        el.classList.add('show');
                        el.classList.remove('hidden');
                        el.classList.remove('collapsed');
                    });
                });
                
                // 3. Expand truncated text
                document.querySelectorAll('.truncated, .clamp, .line-clamp').forEach(el => {
                    el.style.maxHeight = 'none';
                    el.style.webkitLineClamp = 'unset';
                    el.style.display = 'block';
                    el.style.overflow = 'visible';
                    el.classList.remove('truncated');
                    el.classList.remove('clamp');
                });
            };
            
            // Run expansion multiple times with slight delays to catch elements that might
            // appear after other elements are expanded
            expandElements();
            
            // Schedule another expansion after a short delay to catch any elements
            // that might be loaded or displayed dynamically after initial expansion
            setTimeout(expandElements, 300);
        }"""
        )

        # Consistent pause to allow expansions to complete
        page.wait_for_timeout(800)
        
        # Handle subscription popups, cookie consent dialogs, and overlay modals
        logger.info("Removing subscription popups, cookie dialogs, and overlays")
        page.evaluate(
            """() => {
            // Function to remove annoying overlays and popups
            const removePopupsAndOverlays = () => {
                // 1. Handle common overlay modals
                const overlaySelectors = [
                    // Gray/dark overlays that block content
                    '.modal-backdrop', '.overlay', '.popup-overlay', '.modal-overlay',
                    'div[class*="overlay"]', 'div[id*="overlay"]',
                    'div[style*="opacity"][style*="background"]',
                    // Elements with high z-index that might be overlays
                    'div[style*="z-index: 999"]', 'div[style*="z-index: 9999"]',
                    'div[style*="z-index: 10000"]', 'div[style*="z-index: 2147483647"]'
                ];
                
                overlaySelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        try {
                            el.remove();
                        } catch(e) {
                            el.style.display = 'none';
                            el.style.visibility = 'hidden';
                            el.style.opacity = '0';
                            el.style.zIndex = '-1';
                        }
                    });
                });
                
                // 2. Handle subscription popups
                const subscriptionSelectors = [
                    // Common subscription popup containers
                    '.subscription-popup', '.subscribe-popup', '.newsletter-popup',
                    'div[class*="subscribe"]', 'div[id*="subscribe"]',
                    'div[class*="newsletter"]', 'div[id*="newsletter"]',
                    'div[class*="paywall"]', 'div[id*="paywall"]',
                    // Modals and dialogs that might be subscription-related
                    '.modal.show', '.modal:not(.fade)', '.modal[style*="display: block"]',
                    'div[role="dialog"]', 'div[aria-modal="true"]',
                    // Popups with words like subscribe in them
                    'div:not([style*="display: none"]) > div:not([style*="display: none"]) h2:contains("Subscribe")',
                    'div:not([style*="display: none"]) > div:not([style*="display: none"]) h3:contains("Subscribe")'
                ];
                
                subscriptionSelectors.forEach(selector => {
                    try {
                        document.querySelectorAll(selector).forEach(el => {
                            el.remove();
                        });
                    } catch(e) {
                        // Some complex selectors might not be supported, ignore errors
                    }
                });
                
                // 3. Handle cookie consent dialogs
                const cookieSelectors = [
                    // Common cookie consent containers
                    '.cookie-banner', '.cookie-dialog', '.cookie-consent',
                    '.cookies-popup', '.gdpr-banner', '.consent-popup',
                    'div[class*="cookie"]', 'div[id*="cookie"]', 
                    'div[class*="gdpr"]', 'div[id*="gdpr"]',
                    'div[class*="consent"]', 'div[id*="consent"]',
                    // Look for accept buttons to click them first
                    'button[id*="accept"]', 'button[class*="accept"]',
                    'a[id*="accept"]', 'a[class*="accept"]'
                ];
                
                // Try to click accept buttons first
                const acceptButtons = document.querySelectorAll('button, a');
                for (const button of acceptButtons) {
                    const text = button.textContent.toLowerCase();
                    if (text.includes('accept') || text.includes('agree') || 
                        text.includes('got it') || text.includes('i understand') ||
                        text.includes('okay') || text.includes('continue')) {
                        try {
                            button.click();
                            // Short delay to let the click take effect
                            return; // Exit to give the click a chance to work
                        } catch(e) {
                            // Ignore if click fails
                        }
                    }
                }
                
                // Then try to remove cookie dialogs
                cookieSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        try {
                            el.remove();
                        } catch(e) {
                            el.style.display = 'none';
                        }
                    });
                });
                
                // 4. Fix body scroll if it was locked
                document.body.style.overflow = 'auto';
                document.body.style.position = 'static';
                document.documentElement.style.overflow = 'auto';
            };
            
            // Run multiple times with delay to catch things that might reappear
            removePopupsAndOverlays();
            setTimeout(removePopupsAndOverlays, 400);
        }"""
        )
        
        page.wait_for_timeout(600)  # Wait for popup removal to finish
        
        # Second pass with more specific selectors that might trigger UI updates
        logger.info("Performing secondary expansion of interactive elements")
        page.evaluate(
            """() => {
            // Find elements with "show more" or similar text
            const textExpandButtons = Array.from(document.querySelectorAll('button, a, span, div'))
                .filter(el => {
                    const text = el.textContent.toLowerCase();
                    return text.includes('show more') || 
                           text.includes('read more') || 
                           text.includes('expand') ||
                           text.includes('view more') ||
                           text.includes('see all');
                });
                
            // Click these text-based expansion elements
            textExpandButtons.forEach(el => {
                try {
                    el.click();
                } catch (e) {
                    // Ignore errors
                }
            });
        }"""
        )

        # Final consistent delay to allow all expansions to complete
        page.wait_for_timeout(500)

        logger.info("Completed expansion of hidden elements")

    except Exception as e:
        logger.warning(f"Error while expanding hidden elements: {str(e)}")
        # Continue if expansion fails - this is non-critical


def get_webpage_metadata(page: Page, url: str) -> Dict[str, Any]:
    """
    Extract metadata from a webpage.

    Args:
        page: The Playwright page object
        url: The URL of the webpage

    Returns:
        Dictionary containing webpage metadata
    """
    # Consistent delay before metadata extraction
    time.sleep(100 / 1000)
    metadata = {
        "title": page.title(),
        "url": url,
        "accessDate": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Extract the website domain for libraryCatalog field
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if domain.startswith("www."):
        domain = domain[4:]  # Remove www. prefix if present
    metadata["domain"] = domain

    # Try to extract additional metadata
    try:
        # Extract description or abstract if available
        description = page.evaluate(
            """() => {
            const meta = document.querySelector('meta[name="description"]') || 
                         document.querySelector('meta[property="og:description"]');
            return meta ? meta.getAttribute('content') : '';
        }"""
        )
        if description:
            metadata["description"] = description

        # Extract author if available
        author = page.evaluate(
            """() => {
            const meta = document.querySelector('meta[name="author"]') || 
                         document.querySelector('meta[property="article:author"]');
            return meta ? meta.getAttribute('content') : '';
        }"""
        )
        if author:
            metadata["author"] = author

        # Extract publication date if available
        pub_date = page.evaluate(
            """() => {
            const meta = document.querySelector('meta[name="publication_date"]') || 
                         document.querySelector('meta[property="article:published_time"]');
            return meta ? meta.getAttribute('content') : '';
        }"""
        )
        if pub_date:
            metadata["publicationDate"] = pub_date
    except Exception as e:
        logger.warning(f"Error extracting additional metadata: {str(e)}")

    return metadata


class SimpleHTTPServerThread(threading.Thread):
    """
    A thread that runs a simple HTTP server to serve the PDF file locally.
    """

    def __init__(self, directory: str, port: int = 0):
        super().__init__(daemon=True)
        self.directory = directory
        self.port = port
        self.httpd = None
        self._started = threading.Event()

    def run(self):
        """Run the HTTP server in this thread"""
        os.chdir(self.directory)
        handler = http.server.SimpleHTTPRequestHandler
        self.httpd = socketserver.TCPServer(("localhost", self.port), handler)
        self._started.set()
        self.httpd.serve_forever()

    def get_port(self) -> int:
        """Get the port the server is running on"""
        self._started.wait()
        return self.httpd.server_address[1]

    def stop(self):
        """Stop the HTTP server"""
        if self.httpd:
            self.httpd.shutdown()
