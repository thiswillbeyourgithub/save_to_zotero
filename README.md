# Zotero Uploader

A powerful command-line tool for saving webpages as high-quality PDFs and adding them to your Zotero library with proper metadata. Also supports adding existing PDF files to Zotero.

## Personal Motivation

I created this tool after Omnivore shut down, as I was searching for a good multiplatform solution for reading PDFs. Zotero proved to be a promising alternative, especially with its HTML annotation feature. However, I needed something that would work on my phone too. Until a complete solution was available, I decided to build this tool to convert webpages to PDFs for use with Zotero across all my devices.

## Features

- Save any webpage as a high-quality PDF using Playwright's browser automation
- Add PDFs to Zotero with proper metadata extraction
- Support for existing PDF files without webpage sources
- Automatic metadata extraction from webpages and PDF files
- Proper integration with Zotero's storage system and full-text indexing
- Collection support for organizing your Zotero library
- Human-like page scrolling and expansion of hidden content for better PDF captures

## How It Works

Zotero Uploader leverages several technologies to create a seamless experience:

1. **Webpage Capture**: Uses Playwright to render webpages with a real browser engine, capturing all content including JavaScript-rendered content, expandable sections, and proper formatting.

2. **High-Quality PDF Generation**: Creates PDFs with optimal formatting for reading and storage, including automatic expansion of hidden content, proper scrolling to capture all page elements, and preservation of images and formatting.

3. **Metadata Extraction**: Extracts key metadata like title, author, publication date, and description from the webpage to create rich Zotero entries.

4. **Zotero Integration**: Communicates with your Zotero library through both the Zotero API and direct file storage integration to ensure items are properly indexed and accessible.

## Installation

### Prerequisites

- Python 3.8 or higher
- Zotero desktop application (must be running during use)
- Zotero API key (for remote operations)

### Install from source

```bash
# Clone the repository
git clone https://github.com/yourusername/zotero-uploader.git
cd zotero-uploader

# Install dependencies
uv pip install requests fire playwright pypdf2 loguru
uv pip install -U git+https://github.com/urschrei/pyzotero # see https://github.com/urschrei/pyzotero/pull/221

# Install Playwright browsers
playwright install
```

## Usage

### Basic Usage

```bash
# Save a webpage to Zotero
python zotero_uploader.py --url="https://example.com/article"

# Add an existing PDF file to Zotero
python zotero_uploader.py --pdf_path="/path/to/document.pdf"
```

### Advanced Options

```bash
# Full options
python zotero_uploader.py \
  --url="https://example.com/article" \
  --storage_dir="/path/to/zotero/storage" \
  --wait=8000 \
  --api_key="your_zotero_api_key" \
  --library_id="your_library_id" \
  --library_type="user" \
  --collection_name="Research Papers" \
  --verbose=True
```

### Environment Variables

You can set default values using environment variables:

```bash
# Add these to your .bashrc, .zshrc, etc.
export ZOTERO_API_KEY="your_api_key"
export ZOTERO_LIBRARY_ID="your_library_id"
export ZOTERO_LIBRARY_TYPE="user"
export ZOTERO_COLLECTION_NAME="collection_name"
```

## Configuration

### Zotero API Setup

1. Get your Zotero API key from https://www.zotero.org/settings/keys
2. Ensure the API key has read/write access to your library
3. Get your library ID from your Zotero profile URL (e.g., `https://www.zotero.org/username` - username is the library ID for user libraries)

### Storage Directory

By default, the tool uses a standard Zotero storage location. You can specify an alternate location with the `--storage_dir` option.

## Troubleshooting

- **Zotero Must Be Running**: The tool requires Zotero to be running and will attempt to start it if not detected.
- **PDF Generation Issues**: Increase the wait time for complex pages with the `--wait` parameter.
- **Collection Not Found**: Ensure you're using the correct collection key or name.
- **API Authorization Errors**: Verify your API key has proper permissions.

## License

This project is licensed under the GNU General Public License v3.0 - see the LICENSE file for details.

## Contributing

Contributions are very much welcome! We actively encourage the community to submit Pull Requests for any of the roadmap items or your own ideas. Whether it's fixing bugs, improving documentation, or implementing new features, your contributions will help make this project better for everyone.

## Roadmap

Future plans for Zotero Uploader include:

- **PyPI Installation**: Package the tool for easy installation via pip with `pip install zotero-uploader`
- **CLI Tool via uvx**: Create a streamlined command-line interface using uvx for improved user experience
- **HTML Snapshot Support**: Add functionality to save the original HTML of webpages alongside the PDF
- **Batch Processing**: Support for processing multiple URLs or PDFs in a single command
- **Custom PDF Templates**: Allow users to define custom styling for PDF output
- **Integration with Reference Managers**: Extend support beyond Zotero to other reference management systems

If you'd like to contribute to any of these initiatives, please check the issues page or open a new discussion.
