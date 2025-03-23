# save_to_zotero

A powerful command-line tool for saving webpages as high-quality PDFs and adding them to your Zotero library with proper metadata. Also supports adding existing PDF files to Zotero.

**Version:** 0.1.0

**WARNING: THIS IS A WORK IN PROGRESS**

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

- Python 3.8 or higher
- Zotero desktop application (must be running during use)
- Zotero API key (for remote operations)

### Install from source

```bash
# Clone the repository
git clone https://github.com/yourusername/save_to_zotero.git
cd save_to_zotero

# Install dependencies
pip install requests fire playwright PyPDF2 loguru pyzotero>=1.6.11

# Or using uv (faster)
uv pip install requests fire playwright PyPDF2 loguru pyzotero>=1.6.11

# Install Playwright browsers
playwright install chromium
```

## Usage

### Basic Usage

```bash
# Save a webpage to Zotero
python save_to_zotero.py --url="https://example.com/article"

# Add an existing PDF file to Zotero
python save_to_zotero.py --pdf_path="/path/to/document.pdf"

# Add to a specific collection
python save_to_zotero.py --url="https://example.com/article" --collection_name="Research Papers"
```

### Advanced Options

```bash
# Full options
python save_to_zotero.py \
  --url="https://example.com/article" \
  --wait=8000 \
  --api_key="your_zotero_api_key" \
  --library_id="your_library_id" \
  --library_type="user" \
  --collection_name="Research Papers" \
  --verbose=True

# For pages with complex JavaScript content, increase wait time
python save_to_zotero.py --url="https://complex-site.com/article" --wait=10000
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
```

## Configuration

### Zotero API Setup

1. Get your Zotero API key from https://www.zotero.org/settings/keys
2. Ensure the API key has read/write access to your library
3. Get your library ID from your Zotero profile URL:
   - For personal libraries: Your username is your library ID (e.g., `https://www.zotero.org/username`)
   - For group libraries: The numeric ID in the URL (e.g., `https://www.zotero.org/groups/1234567`)

### Connector Configuration

The tool communicates with Zotero through its connector API, which requires Zotero to be running. By default, it connects to:

- Host: http://127.0.0.1
- Port: 23119

These can be configured using environment variables if needed.

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
- **PDF Scrolling Problems**: For very long pages, try breaking the capture into sections.

## License

This project is licensed under the GNU General Public License v3.0 - see the LICENSE file for details.

## Contributing

Contributions are very much welcome! We actively encourage the community to submit Pull Requests for any of the roadmap items or your own ideas. Whether it's fixing bugs, improving documentation, or implementing new features, your contributions will help make this project better for everyone.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/save_to_zotero.git
cd save_to_zotero

# Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"  # Once setup.py is implemented
```

## Roadmap

Future plans for save_to_zotero include:

- **PyPI Installation**: Package the tool for easy installation via pip with `pip install save-to-zotero`
- **CLI Tool via entry points**: Create a streamlined command-line interface with proper entry points
- **Enhanced Metadata Extraction**: Further improve metadata extraction for more accurate bibliographic records
- **Batch Processing**: Support for processing multiple URLs or PDFs in a single command
- **Custom PDF Templates**: Allow users to define custom styling for PDF output
- **Tag Support**: Add ability to apply tags to saved items
- **Integration with Browser Extensions**: Develop browser extensions to send URLs directly to the tool
- **Site-specific Handling**: Special handling for common sites like academic journals and news publications
- **Proxy Support**: Enable use with institutional proxies for accessing paywalled content
- **PDF Text Layer**: Ensure PDFs have searchable text layers

If you'd like to contribute to any of these initiatives, please check the issues page or open a new discussion.

## Credits

- [Pyzotero](https://github.com/urschrei/pyzotero) - Python client for the Zotero API
