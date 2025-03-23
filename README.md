# save_to_zotero

A powerful command-line tool for saving webpages as high-quality PDFs and adding them to your Zotero library with proper metadata. Also supports adding existing PDF files to Zotero.

Note that this tool is quite new so if you find any bugs please open an issue!

## Personal Motivation

I created this tool after [Omnivore](https://github.com/omnivore-app/omnivore) shut down, as I was searching for a good multiplatform solution for reading PDFs. Zotero proved to be a promising alternative, especially with its HTML annotation feature. However, I needed something that would work on my phone too. Until a complete solution was available, I decided to build this tool to convert webpages to PDFs for use with Zotero across all my devices. Once saved via this tool, all content is fully accessible on your phone, tablet, and any other device with a Zotero client.

## Features

- Save any webpage as a high-quality PDF using Playwright's browser automation
- Works whether you use Zotero's or WebDAV backend for storage
- PDFs and webpages saved are accessible on all Zotero clients (desktop, mobile, tablet)
- Add PDFs to Zotero with proper metadata extraction
- Support for existing PDF files without webpage sources
- Automatic metadata extraction from webpages (title, description, author, publication date)
- Integration with Zotero's connector API for better reliability
- Collection support for organizing your Zotero library (by name or key)
- Tag support for better organization of your Zotero library
- Human-like page scrolling and expansion of hidden content for better PDF captures
- Intelligent handling of dynamic content like accordions and dropdowns
- Smart title extraction for better file naming

## How It Works

save_to_zotero leverages several technologies to create a seamless experience:

1. **Webpage Capture**: Uses Playwright to render webpages with a real browser engine, capturing all content including JavaScript-rendered content, expandable sections, and proper formatting.

2. **High-Quality PDF Generation**: Creates PDFs with optimal formatting for reading and storage, including automatic expansion of hidden content, proper scrolling to capture all page elements, and preservation of images and formatting.

3. **Metadata Extraction**: Extracts key metadata (title, description, author, publication date) from the webpage to create rich Zotero entries.

4. **Zotero Integration**: Communicates with your Zotero library through both the Zotero API and the Zotero Connector API to ensure items are properly indexed and accessible on all your devices (computer, phone, tablet) regardless of whether you use Zotero's storage or WebDAV.

5. **Anti-Detection Measures**: Uses randomized user agents and anti-fingerprinting techniques to bypass website restrictions.

## Installation

### Prerequisites

- Python 3.7 or higher
- Zotero desktop application (must be running during use)
- Zotero API key (for remote operations)

### Install from PyPI

```bash
uv pip install save-to-zotero
```

### Install from source

```bash
# Clone the repository
git clone https://github.com/thiswillbeyourgithub/save_to_zotero.git
cd save_to_zotero

# Install the package and dependencies
pip install -e .
```

## Usage

### Basic Usage

Note: to launch save-to-zotero you have three possibilities:

1. Preferred: `uvx save-to-zotero@latest [args]`. This will always use the latest version.
2. `python -m save_to_zotero [args]`
3. `save-to-zotero [args]`

```bash
# Save a webpage to Zotero
uvx save-to-zotero@latest --url="https://example.com/article"

# Add an existing PDF file to Zotero
uvx save-to-zotero@latest --pdf_path="/path/to/document.pdf"

# Add to a specific collection
uvx save-to-zotero@latest --url="https://example.com/article" --collection_name="Research Papers"

# Add tags to the item
uvx save-to-zotero@latest --url="https://example.com/article" --tags="research,important,to-read"
```

### Advanced Options

```bash
# Full options
uvx save-to-zotero \
  --url="https://example.com/article" \
  --wait=8000 \
  --api_key="your_zotero_api_key" \
  --library_id="your_library_id" \
  --library_type="user" \
  --collection_name="Research Papers" \
  --tags="research,important" \
  --verbose=True

# For pages with complex JavaScript content, increase wait time
uvx save-to-zotero --url="https://complex-site.com/article" --wait=10000
```

### Environment Variables

You can set default values using environment variables:

```bash
# Add these to your .bashrc, .zshrc, etc.
export ZOTERO_API_KEY="your_api_key"
export ZOTERO_LIBRARY_ID="your_library_id"
export ZOTERO_LIBRARY_TYPE="user"  # "user" or "group"
export ZOTERO_COLLECTION_NAME="collection_name"
export ZOTERO_CONNECTOR_HOST="http://127.0.0.1"  # Default connector host
export ZOTERO_CONNECTOR_PORT="23119"  # Default connector port
export ZOTERO_USER_AGENT="your_custom_user_agent"  # Optional
export ZOTERO_BROWSER_USER_DATA_DIR="/path/to/user/data/dir"  # Optional: for persistent cookies/login sessions
```

## Configuration

### Connector Configuration

The tool communicates with Zotero through its connector API, which requires Zotero to be running. By default, it connects to:

- Host: http://127.0.0.1
- Port: 23119

These can be configured using environment variables if needed.

### Browser Configuration

By default, save_to_zotero runs in headless mode (invisible browser) for PDF generation. However, you can:

1. **Use Existing Browser Cookies**: Set the `ZOTERO_BROWSER_USER_DATA_DIR` environment variable to your browser's user data directory to utilize cookies already stored in your browser for sites that require login
2. **Run in Visible Mode**: When a user data directory is specified, the browser automatically runs in visible mode (non-headless), allowing you to see the page capture process

⚠️ **Important Warning**: When using a browser user data directory, avoid using the same browser profile simultaneously while save_to_zotero is running, as this could cause conflicts and potentially corrupt your browser profile

Example:
```bash
# Set path to your existing Chrome/Chromium user data directory
export ZOTERO_BROWSER_USER_DATA_DIR="/home/username/.config/chromium/Default"  # Linux example
# or
export ZOTERO_BROWSER_USER_DATA_DIR="C:\\Users\\username\\AppData\\Local\\Google\\Chrome\\User Data\\Default"  # Windows example
# or
export ZOTERO_BROWSER_USER_DATA_DIR="/Users/username/Library/Application Support/Google/Chrome/Default"  # macOS example

# Run the tool - it will use your existing browser cookies and run in visible mode
uvx save-to-zotero@latest --url="https://example.com/login-required-page"
```

## Troubleshooting

- **Zotero Must Be Running**: The tool requires the Zotero desktop application to be running.
- **PDF Generation Issues**: 
  - Increase the wait time for complex pages with the `--wait` parameter (default is 5000ms)
  - For pages with infinite scroll, consider capturing a specific section rather than the entire page
- **Collection Not Found**: Ensure you're using the correct collection name exactly as it appears in Zotero.
- **API Authorization Errors**: Verify your API key has proper permissions and is entered correctly.
- **Connector Issues**: 
  - Ensure Zotero is running before executing the command
  - Check if Zotero is using a non-standard port (can be verified in Zotero's Advanced preferences)
- **Login-Required Pages**:
  - For pages that require login, set the `ZOTERO_BROWSER_USER_DATA_DIR` environment variable to point to your existing browser profile to use already stored cookies
  - Ensure you close the browser or don't use the same profile while save_to_zotero is running
  - You can also create a dedicated browser profile just for save_to_zotero to avoid conflicts

## License

This project is licensed under the GNU General Public License v3.0 - see the LICENSE file for details.

## Contributing

Contributions are very much welcome! We actively encourage the community to submit Pull Requests for any of the roadmap items or your own ideas. Whether it's fixing bugs, improving documentation, or implementing new features, your contributions will help make this project better for everyone.


## Roadmap

Future plans for save_to_zotero include:

- **Implement Testing with pytest**: Add comprehensive test coverage using pytest to ensure reliability and facilitate future development

If you'd like to contribute to any of these initiatives, please check the issues page or open a new discussion.

## Credits

- [Pyzotero](https://github.com/urschrei/pyzotero) - Python client for the Zotero API
