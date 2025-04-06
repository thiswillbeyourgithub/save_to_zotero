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


def save_webpage_as_pdf(url: str, output_path: str, wait_for_load: int = 5000, verbose: bool = False) -> dict:
    """
    Save a webpage as a PDF using Playwright with human-like behavior.

    Args:
        url: The URL of the webpage to save
        output_path: The path where the PDF will be saved
        wait_for_load: Base time to wait in ms for page to fully load (will be randomized)
        verbose: Whether to run in verbose mode (also sets headless to False)

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
    
    # Determine headless mode from environment variable (default to True) or verbose flag
    # If verbose is True, set headless_mode to False to see the browser UI
    env_headless = os.environ.get("SAVE_TO_ZOTERO_HEADLESS", "true").lower() != "false"
    headless_mode = env_headless and not verbose
    logger.info(f"Browser headless mode: {headless_mode}")

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
            logger.info(f"Running browser with user data directory (headless: {headless_mode})")
            
            # Use launch_persistent_context for user data directories
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless_mode,
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
            # Set headless mode based on environment variable
            launch_args["headless"] = headless_mode
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
        viewport_height = page.viewport_size["height"]
        
        # Calculate number of scrolls with overlap
        num_scrolls = max(3, int(height / (viewport_height * 0.8)) + 1)
        
        logger.info(f"Scrolling through page with {num_scrolls} steps")
        
        for i in range(num_scrolls):
            # Calculate scroll position with 20% overlap between scrolls
            scroll_to = min(i * (viewport_height * 0.8), height)
            
            # Scroll with smooth behavior
            page.evaluate(f"window.scrollTo({{top: {scroll_to}, behavior: 'smooth'}})")
            
            # Pause to let content load
            page.wait_for_timeout(600)
            
            # Slight jitter in scroll position to trigger lazy-loading
            if i > 0 and i < num_scrolls - 1:
                jitter = random.randint(-30, 30)
                page.evaluate(f"window.scrollBy(0, {jitter})")
                page.wait_for_timeout(200)
                
    except Exception as e:
        logger.warning(f"Error during scrolling simulation: {str(e)}")
        # Continue if scrolling fails - this is non-critical


def _expand_hidden_elements(page: Page) -> None:
    """
    Expand dropdowns, accordions, and other hidden content to ensure
    all text is visible in the PDF without navigating away from the current page.

    Args:
        page: The Playwright page object
    """
    try:
        # Store the current URL to check against later
        current_url = page.url
        logger.info(f"Current URL before expansion: {current_url}")
        
        # First pass: Basic content expansion with minimal risk of navigation
        logger.info("Expanding standard content elements")
        page.evaluate("""() => {
            // Basic content visibility function
            const showHiddenContent = () => {
                // 1. Open all details elements
                document.querySelectorAll('details').forEach(el => {
                    el.setAttribute('open', 'true');
                    el.open = true;
                    el.style.display = 'block';
                    
                    // Make all children of details visible
                    Array.from(el.children).forEach(child => {
                        if (child.tagName !== 'SUMMARY') {
                            child.style.display = 'block';
                            child.style.visibility = 'visible';
                        }
                    });
                });
                
                // 2. Make hidden accessible content visible
                const accessibilitySelectors = [
                    '[aria-hidden="true"]',
                    '[aria-expanded="false"]',
                    '.sr-only', '.screen-reader-text', '.visually-hidden',
                    '[hidden]',
                    '[role="tabpanel"]'
                ];
                
                accessibilitySelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        // Basic show operation
                        if (selector === '[aria-hidden="true"]') {
                            el.setAttribute('aria-hidden', 'false');
                        } else if (selector === '[aria-expanded="false"]') {
                            el.setAttribute('aria-expanded', 'true');
                        } else if (selector === '[hidden]') {
                            el.removeAttribute('hidden');
                        }
                        
                        // Apply visibility styles
                        el.style.display = 'block';
                        el.style.visibility = 'visible';
                        el.style.height = 'auto';
                        el.style.maxHeight = 'none';
                        el.style.overflow = 'visible';
                    });
                });
                
                // 3. Expand truncated text
                document.querySelectorAll('.truncated, .clamp, .line-clamp').forEach(el => {
                    el.style.maxHeight = 'none';
                    el.style.webkitLineClamp = 'unset';
                    el.style.display = 'block';
                    el.style.overflow = 'visible';
                });
                
                // 4. Show elements commonly used to hide content
                const contentSelectors = [
                    '.collapse', '.accordion-content', '.dropdown-menu',
                    '.hidden-content', '.expandable-content',
                    '.read-more-content', '.show-more-content'
                ];
                
                contentSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        el.style.display = 'block';
                        el.style.visibility = 'visible';
                        el.style.height = 'auto';
                        el.style.opacity = '1';
                        el.classList.add('show');
                        el.classList.add('active');
                        el.classList.remove('hidden');
                        el.classList.remove('collapsed');
                    });
                });
            };
            
            // Run content expansion
            showHiddenContent();
            // Second pass to catch any elements modified by the first pass
            setTimeout(showHiddenContent, 300);
        }""")
        
        # Allow time for the first expansion pass
        page.wait_for_timeout(400)
        
        # Second pass: Remove overlays and distractions
        logger.info("Removing overlays and popups")
        page.evaluate("""() => {
            // Remove popups and overlays
            const removeOverlays = () => {
                // Common overlay and popup selectors
                const overlaySelectors = [
                    '.modal-backdrop', '.overlay', '.popup-overlay',
                    '.cookie-banner', '.cookie-consent', '.gdpr-banner',
                    '.subscription-popup', '.newsletter-popup', '.paywall'
                ];
                
                overlaySelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        try {
                            el.remove();
                        } catch(e) {
                            el.style.display = 'none';
                        }
                    });
                });
                
                // Fix body scroll if it was locked
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
            };
            
            removeOverlays();
        }""")
        
        # Allow time for overlay removal
        page.wait_for_timeout(300)
        
        # Third pass: Safe interaction with content expanders
        logger.info("Expanding interactive elements")
        page.evaluate("""(currentUrl) => {
            // Safely interact with elements that expand content
            const safelyExpandInteractive = () => {
                // Helper to check if element would cause navigation
                const wouldNavigate = (el) => {
                    if (el.tagName === 'A') {
                        const href = el.getAttribute('href');
                        if (href && 
                            href !== '#' && 
                            !href.startsWith('#') && 
                            !href.startsWith('javascript:')) {
                            return true;
                        }
                    }
                    return false;
                };
                
                // Find and click "read more"/"show more" buttons that won't navigate
                const expandButtons = Array.from(document.querySelectorAll('button, a, span, div'))
                    .filter(el => {
                        const text = (el.textContent || '').toLowerCase();
                        return (text.includes('more') || text.includes('expand')) && 
                               !wouldNavigate(el);
                    });
                
                expandButtons.forEach(el => {
                    try {
                        const beforeUrl = window.location.href;
                        el.click();
                        
                        // Revert if navigation occurred
                        if (window.location.href !== beforeUrl) {
                            history.pushState(null, '', beforeUrl);
                        }
                    } catch (e) {
                        // Ignore click errors
                    }
                });
                
                // Expand common UI patterns
                const expandableSelectors = [
                    'details:not([open])',
                    '.accordion:not(.active)',
                    '[aria-expanded="false"]',
                    '.faq-question:not(.active)'
                ];
                
                expandableSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        if (!wouldNavigate(el)) {
                            try {
                                el.click();
                            } catch(e) {
                                // If clicking fails, try direct attribute manipulation
                                if (selector === 'details:not([open])') {
                                    el.setAttribute('open', 'true');
                                    el.open = true;
                                } else if (selector === '[aria-expanded="false"]') {
                                    el.setAttribute('aria-expanded', 'true');
                                }
                                el.classList.add('active');
                                el.classList.add('show');
                            }
                        }
                    });
                });
            };
            
            safelyExpandInteractive();
        }""", current_url)
        
        # Allow time for interactive elements
        page.wait_for_timeout(500)
        
        # Final check and expansion for any remaining hidden content
        logger.info("Final content expansion pass")
        page.evaluate("""() => {
            // Final pass to ensure maximum content visibility
            const finalExpansion = () => {
                // 1. Ensure all content heights are adequate
                document.querySelectorAll('[style*="height"], [style*="max-height"]').forEach(el => {
                    // Skip truly huge elements to avoid breaking layout
                    if (el.clientHeight < 1000 && el.textContent.trim().length > 10) {
                        el.style.height = 'auto';
                        el.style.maxHeight = 'none';
                    }
                });
                
                // 2. Final check for display:none elements with content
                document.querySelectorAll('[style*="display: none"], [style*="visibility: hidden"]').forEach(el => {
                    // Only make visible if it contains actual content
                    if (el.textContent.trim().length > 20 || 
                        el.querySelectorAll('p, h1, h2, h3, h4, h5, h6').length > 0) {
                        el.style.display = 'block';
                        el.style.visibility = 'visible';
                    }
                });
                
                // 3. Final pass for details elements
                document.querySelectorAll('details').forEach(el => {
                    el.setAttribute('open', 'true');
                    el.open = true;
                    el.style.display = 'block';
                });
            };
            
            finalExpansion();
        }""")
        
        # Allow final expansions to take effect
        page.wait_for_timeout(500)
        
        # Check if URL changed and restore if needed
        if page.url != current_url:
            logger.warning(f"URL changed to {page.url}, navigating back to original")
            page.goto(current_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(500)
        
        logger.info("Completed content expansion successfully")
        
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
