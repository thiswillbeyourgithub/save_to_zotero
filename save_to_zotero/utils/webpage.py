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
    all text is visible in the PDF without navigating away from the current page.
    
    Leverages accessibility features to expose content that may be hidden
    but accessible to screen readers.

    Args:
        page: The Playwright page object
    """
    try:
        # Store the current URL to check against later
        current_url = page.url
        logger.info(f"Current URL before expansion: {current_url}")
        
        # Enable accessibility features to better expose hidden content
        logger.info("Enabling accessibility mode to expose hidden content")
        page.evaluate("""() => {
            // Add attribute to document to indicate we want all content exposed
            document.documentElement.setAttribute('data-force-accessibility', 'true');
            
            // Some sites check for screen readers - let's pretend to be one
            // These are common properties checked to detect screen readers
            Object.defineProperty(window, 'speechSynthesis', {
                value: { speak: function() {} },
                configurable: true
            });
            
            // Mimic some common screen reader detection flags
            if (!window.hasOwnProperty('onvoiceschanged')) {
                Object.defineProperty(window, 'onvoiceschanged', {
                    value: function() {},
                    configurable: true
                });
            }
        }""")
        
        # Consistent small delay before expanding elements
        time.sleep(200 / 1000)

        # First, process accessibility-specific elements to expose content for screen readers
        logger.info("Processing accessibility attributes to expose hidden content")
        page.evaluate("""() => {
            // Function to expose content hidden via ARIA attributes
            const exposeAccessibleContent = () => {
                // 1. Make all aria-hidden="true" elements visible
                document.querySelectorAll('[aria-hidden="true"]').forEach(el => {
                    el.setAttribute('aria-hidden', 'false');
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                });
                
                // 2. Expand all elements with aria-expanded="false"
                document.querySelectorAll('[aria-expanded="false"]').forEach(el => {
                    el.setAttribute('aria-expanded', 'true');
                    
                    // Find the controlled element if specified
                    const controlsId = el.getAttribute('aria-controls');
                    if (controlsId) {
                        const controlledEl = document.getElementById(controlsId);
                        if (controlledEl) {
                            controlledEl.style.display = 'block';
                            controlledEl.style.visibility = 'visible';
                            controlledEl.setAttribute('aria-hidden', 'false');
                        }
                    }
                });
                
                // 3. Show elements that might be conditionally displayed for screen readers
                document.querySelectorAll('.sr-only, .screen-reader-text, .visually-hidden, .visually-hidden-focusable').forEach(el => {
                    // Remove special positioning that hides from sighted users but keeps for screen readers
                    el.style.position = 'static';
                    el.style.width = 'auto';
                    el.style.height = 'auto';
                    el.style.overflow = 'visible';
                    el.style.clip = 'auto';
                    el.style.clipPath = 'none';
                    el.style.whiteSpace = 'normal';
                    el.style.margin = '1em 0';  // Add some spacing
                    
                    // Add visual indication this was screen-reader only content
                    el.style.border = '1px dashed #999';
                    el.style.padding = '0.5em';
                    el.style.backgroundColor = '#f8f8f8';
                });
                
                // 4. Process elements that use the "hidden" attribute
                document.querySelectorAll('[hidden]').forEach(el => {
                    // Check if this might contain useful content
                    if (el.textContent.trim().length > 20 || 
                        el.querySelectorAll('p, h1, h2, h3, h4, h5, h6').length > 0) {
                        el.removeAttribute('hidden');
                        el.style.display = 'block';
                    }
                });
                
                // 5. Find and expand ARIA tabpanels that might be hidden
                document.querySelectorAll('[role="tab"]').forEach(tab => {
                    // Mark tab as selected/active
                    tab.setAttribute('aria-selected', 'true');
                    tab.classList.add('active');
                    
                    // Find and show the associated tabpanel
                    const panelId = tab.getAttribute('aria-controls');
                    if (panelId) {
                        const panel = document.getElementById(panelId);
                        if (panel) {
                            panel.style.display = 'block';
                            panel.style.visibility = 'visible';
                        }
                    }
                });
            };
            
            // Run accessibility content exposure multiple times
            exposeAccessibleContent();
            setTimeout(exposeAccessibleContent, 500);
        }""")
        
        # Allow time for accessibility processing
        page.wait_for_timeout(600)
        
        # Now execute JavaScript to expand common interactive elements without causing navigation
        page.evaluate(
            """(currentUrl) => {
            // Function to check if an element is likely to cause navigation
            const wouldCauseNavigation = (element) => {
                // Check for links with external hrefs
                if (element.tagName === 'A') {
                    const href = element.getAttribute('href');
                    // Skip if it's an external link, absolute path, or not a fragment/hash link
                    if (href && 
                        href !== '#' && 
                        !href.startsWith('#') && 
                        !href.startsWith('javascript:') &&
                        !element.getAttribute('role')) {
                        return true;
                    }
                    
                    // Check if it has target="_blank" which opens in new tab/window
                    if (element.getAttribute('target') === '_blank') {
                        return true;
                    }
                }
                
                // Check for buttons or other elements with onclick that might navigate
                if (element.hasAttribute('onclick')) {
                    const onclickValue = element.getAttribute('onclick');
                    if (onclickValue.includes('location.href') || 
                        onclickValue.includes('window.location') || 
                        onclickValue.includes('navigate')) {
                        return true;
                    }
                }
                
                // Check for typical navigation classes or IDs
                const elementClasses = element.className.toLowerCase();
                const elementId = (element.id || '').toLowerCase();
                const navigationTerms = ['nav-link', 'navbar', 'menu-item', 'pagination'];
                
                for (const term of navigationTerms) {
                    if (elementClasses.includes(term) || elementId.includes(term)) {
                        return true;
                    }
                }
                
                return false;
            };
            
            // Function to expand elements
            const expandElements = () => {
                // 1. Click on common dropdown/accordion triggers - only those that won't navigate
                const clickSelectors = [
                    // Common accordion/dropdown triggers
                    'details:not([open])',  // Include details elements to expand them
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
                
                // Process each type of clickable element, checking if it would cause navigation
                clickSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        try {
                            // Only click if element won't cause navigation
                            if (!wouldCauseNavigation(el)) {
                                // Store url before click
                                const beforeUrl = window.location.href;
                                
                                // Click the element
                                el.click();
                                
                                // Check if URL changed (navigation occurred)
                                if (window.location.href !== beforeUrl) {
                                    console.warn('Navigation detected, attempting to go back');
                                    // Try to restore previous URL
                                    history.pushState(null, '', beforeUrl);
                                }
                            }
                        } catch (e) {
                            // Ignore errors if element can't be clicked
                        }
                    });
                });
                
                // 2. Force-expand elements by setting attributes and styles
                // Explicitly open all details elements to make their content visible in PDF
                const showSelectors = [
                    '.collapse:not(.show)',
                    '.accordion-content', 
                    '.dropdown-menu',
                    '.hidden-content',
                    '[aria-hidden="true"]',
                    // Common accessibility-hiding classes
                    '.sr-only', '.screen-reader-text', '.visually-hidden',
                    // Additional selectors for potentially hidden but important content
                    '[role="tabpanel"]', '[role="dialog"]', '[role="menu"]',
                    '[role="tooltip"]', '[role="alert"]', '[role="status"]'
                ];
                
                // Explicitly open all details elements to ensure content is visible in PDF
                document.querySelectorAll('details').forEach(el => {
                    el.setAttribute('open', 'true');
                });
                
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
            
            // Run expansion multiple times with increasing delays to catch elements
            // that appear incrementally after previous expansions or depend on animations
            expandElements();
            
            // Multiple passes with increasing delays to catch cascading expansions
            setTimeout(expandElements, 300);
            setTimeout(expandElements, 800);
            setTimeout(expandElements, 1500); 
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
            
            // Run multiple times with progressive delays to catch popups that might reappear
            // or load dynamically after initial user interaction
            removePopupsAndOverlays();
            setTimeout(removePopupsAndOverlays, 400);
            setTimeout(removePopupsAndOverlays, 1000);
            setTimeout(removePopupsAndOverlays, 2000);
        }"""
        )
        
        page.wait_for_timeout(600)  # Wait for popup removal to finish
        
        # Check if the page URL has changed after removing popups
        if page.url != current_url:
            logger.warning(f"URL changed to {page.url} after popup removal, attempting to navigate back")
            page.goto(current_url, wait_until="networkidle", timeout=30000)
        
        # Process any additional accessibility-specific content
        logger.info("Processing additional accessibility features")
        page.evaluate("""() => {
            // Function to process elements that might have alternative text representations
            const processAccessibilityText = () => {
                // 1. Make aria-label content visible when it might contain useful information
                document.querySelectorAll('[aria-label]:not(img):not(input):not(button)').forEach(el => {
                    const ariaLabel = el.getAttribute('aria-label');
                    // Only process substantive aria-labels (not just "close" or "menu")
                    if (ariaLabel && ariaLabel.length > 15 && !el.textContent.includes(ariaLabel)) {
                        // Create a visible representation of the aria-label text
                        const labelEl = document.createElement('div');
                        labelEl.textContent = ariaLabel;
                        labelEl.style.padding = '0.5em';
                        labelEl.style.margin = '0.5em 0';
                        labelEl.style.borderLeft = '3px solid #666';
                        labelEl.style.backgroundColor = '#f0f0f0';
                        labelEl.style.fontStyle = 'italic';
                        labelEl.style.fontSize = '0.9em';
                        
                        // Add the label text visibly near the element
                        el.appendChild(labelEl);
                    }
                });
                
                // 2. Make aria-description content visible
                document.querySelectorAll('[aria-description]').forEach(el => {
                    const description = el.getAttribute('aria-description');
                    if (description && description.length > 10) {
                        const descEl = document.createElement('div');
                        descEl.textContent = description;
                        descEl.style.color = '#666';
                        descEl.style.fontStyle = 'italic';
                        descEl.style.margin = '0.3em 0';
                        el.appendChild(descEl);
                    }
                });
                
                // 3. Look for longdesc attributes on images (rarely used but valuable)
                document.querySelectorAll('img[longdesc]').forEach(img => {
                    const longdesc = img.getAttribute('longdesc');
                    if (longdesc) {
                        const descEl = document.createElement('div');
                        descEl.textContent = `Image description: ${longdesc}`;
                        descEl.style.fontStyle = 'italic';
                        descEl.style.margin = '0.5em 0';
                        descEl.style.maxWidth = img.width + 'px';
                        img.parentNode.insertBefore(descEl, img.nextSibling);
                    }
                });
                
                // 4. Process figure elements with figcaption to ensure captions are visible
                document.querySelectorAll('figure').forEach(fig => {
                    const caption = fig.querySelector('figcaption');
                    if (caption) {
                        caption.style.display = 'block';
                        caption.style.visibility = 'visible';
                        caption.style.margin = '0.5em 0';
                    }
                });
            };
            
            processAccessibilityText();
        }""")
        
        # Allow time for accessibility processing
        page.wait_for_timeout(500)
        
        # Multiple passes with more specific selectors that might trigger UI updates
        logger.info("Performing multiple passes of interactive element expansion")
        
        # Define how many passes to perform (3-4 is usually sufficient)
        expansion_passes = 3
        
        for pass_num in range(expansion_passes):
            logger.info(f"Expansion pass {pass_num + 1}/{expansion_passes}")
            page.evaluate(
            """(currentUrl) => {
            // Helper to check if element would cause navigation
            const wouldCauseNavigation = (element) => {
                // For links, check href
                if (element.tagName === 'A') {
                    const href = element.getAttribute('href');
                    if (href && 
                        href !== '#' && 
                        !href.startsWith('#') && 
                        !href.startsWith('javascript:')) {
                        return true;
                    }
                }
                
                // Check for onClick handlers that might navigate
                if (element.hasAttribute('onclick')) {
                    const onClick = element.getAttribute('onclick');
                    if (onClick.includes('location') || onClick.includes('href')) {
                        return true;
                    }
                }
                
                return false;
            };
            
            // Find elements with "show more" or similar text
            const textExpandButtons = Array.from(document.querySelectorAll('button, a, span, div'))
                .filter(el => {
                    const text = (el.textContent || '').toLowerCase();
                    return (text.includes('show more') || 
                           text.includes('read more') || 
                           text.includes('expand') ||
                           text.includes('view more') ||
                           text.includes('see all')) && 
                           !wouldCauseNavigation(el);
                });
                
            // Click these text-based expansion elements safely
            textExpandButtons.forEach(el => {
                try {
                    // Remember URL before click
                    const beforeUrl = window.location.href;
                    
                    // Click the element
                    el.click();
                    
                    // Check if URL changed
                    if (window.location.href !== beforeUrl) {
                        console.warn('Navigation detected, reverting');
                        history.pushState(null, '', beforeUrl);
                    }
                } catch (e) {
                    // Ignore errors
                }
            });
        }""", current_url)

            # Increasing timeouts for each pass to allow cascading elements to appear
            page.wait_for_timeout(500 + 300 * pass_num)
        
        # Final check to ensure we're still on the original page
        if page.url != current_url:
            logger.warning(f"URL changed to {page.url} after expansion, navigating back to original")
            page.goto(current_url, wait_until="networkidle", timeout=30000)
            # Wait again after returning to original page
            page.wait_for_timeout(800)
        
        # Do one final expansion pass after everything else is done
        logger.info("Performing final expansion pass with accessibility focus")
        page.evaluate("""() => {
            const expandFinalElements = () => {
                // Force-expand any remaining elements by looking for specific CSS patterns
                document.querySelectorAll('[style*="height: 0"]').forEach(el => {
                    el.style.height = 'auto';
                    el.style.maxHeight = 'none';
                });
                
                // Final accessibility-specific processing
                // 1. Process any remaining ARIA live regions which often contain dynamic content
                document.querySelectorAll('[aria-live]').forEach(el => {
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                    el.style.height = 'auto';
                    el.style.overflow = 'visible';
                });
                
                // 2. Look for any element with aria attributes that might contain hidden content
                document.querySelectorAll('[aria-describedby], [aria-details], [aria-labelledby]').forEach(el => {
                    // Process elements referenced by ID in these attributes
                    ['aria-describedby', 'aria-details', 'aria-labelledby'].forEach(attr => {
                        const ids = el.getAttribute(attr);
                        if (ids) {
                            ids.split(/\s+/).forEach(id => {
                                const referenced = document.getElementById(id);
                                if (referenced) {
                                    referenced.style.display = 'block';
                                    referenced.style.visibility = 'visible';
                                    referenced.style.height = 'auto';
                                    referenced.style.overflow = 'visible';
                                    referenced.style.position = 'static';
                                }
                            });
                        }
                    });
                });
                
                document.querySelectorAll('[style*="display: none"]').forEach(el => {
                    // Check if this might be an important content element (not a utility element)
                    const classes = el.className.toLowerCase();
                    const id = (el.id || '').toLowerCase();
                    
                    // Skip likely utility/navigation elements
                    if (classes.includes('menu') || 
                        classes.includes('nav') || 
                        id.includes('menu') || 
                        id.includes('nav')) {
                        return;
                    }
                    
                    // Make potentially useful hidden content visible
                    if (classes.includes('content') || 
                        classes.includes('text') || 
                        classes.includes('body') ||
                        el.querySelector('p, h1, h2, h3, h4, h5, h6, article')) {
                        el.style.display = 'block';
                        el.style.visibility = 'visible';
                    }
                });
                
                // Try to make all text visible by increasing any small heights
                document.querySelectorAll('div, p, section, article').forEach(el => {
                    const computedStyle = window.getComputedStyle(el);
                    const height = parseFloat(computedStyle.height);
                    // If element has suspiciously small height but contains text
                    if (height < 50 && el.textContent.trim().length > 10) {
                        el.style.height = 'auto';
                        el.style.maxHeight = 'none';
                        el.style.overflow = 'visible';
                    }
                });
            };
            
            // Run multiple times
            expandFinalElements();
            setTimeout(expandFinalElements, 300);
        }""")
        
        # Final wait to ensure all expansions take effect
        page.wait_for_timeout(800)
        
        logger.info("Completed multiple passes of hidden element expansion, still on original URL")

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
