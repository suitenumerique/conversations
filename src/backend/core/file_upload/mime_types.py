"""MIME type lists gating which files may be uploaded and sent to the LLM."""

# Blocked at upload time: executables, scripts, archives and macro-enabled
# documents that have no business being attached to a conversation.
UNSAFE_MIME_TYPES = [
    # Executable Files
    "application/x-msdownload",
    "application/x-bat",
    "application/x-dosexec",
    "application/x-sh",
    "application/x-ms-dos-executable",
    "application/x-msi",
    "application/java-archive",
    "application/octet-stream",
    # Dynamic Web Pages
    "application/x-httpd-php",
    "application/x-asp",
    "application/x-aspx",
    "application/jsp",
    "application/xhtml+xml",
    "application/x-python-code",
    "application/x-perl",
    "text/html",
    "text/javascript",
    "text/x-php",
    # System Files
    "application/x-msdownload",
    "application/x-sys",
    "application/x-drv",
    "application/cpl",
    "application/x-apple-diskimage",
    # Script Files
    "application/javascript",
    "application/x-vbscript",
    "application/x-powershell",
    "application/x-shellscript",
    # Compressed/Archive Files
    "application/zip",
    "application/x-tar",
    "application/gzip",
    "application/x-bzip2",
    "application/x-7z-compressed",
    "application/x-rar",
    "application/x-rar-compressed",
    "application/x-compress",
    "application/x-lzma",
    # Macros in Documents
    "application/vnd.ms-word",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.ms-word.document.macroenabled.12",
    "application/vnd.ms-excel.sheet.macroenabled.12",
    "application/vnd.ms-powerpoint.presentation.macroenabled.12",
    # Disk Images & Virtual Disk Files
    "application/x-iso9660-image",
    "application/x-vmdk",
    "application/x-apple-diskimage",
    "application/x-dmg",
    # Other Dangerous MIME Types
    "application/x-ms-application",
    "application/x-msdownload",
    "application/x-shockwave-flash",
    "application/x-silverlight-app",
    "application/x-java-vm",
    "application/x-bittorrent",
    "application/hta",
    "application/x-csh",
    "application/x-ksh",
    "application/x-ms-regedit",
    "application/x-msdownload",
    "application/xml",
]

# Accepted for RAG: document, text and image formats the parsers can handle.
RAG_ACCEPTED_MIME_TYPES = [
    # docx files
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # pptx files
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # xlsx and xls files
    "application/vnd.ms-excel",
    "application/excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # txt and csv files
    "text/plain",
    "text/csv",
    "application/csv",
    # pdf files
    "application/pdf",
    # html files
    "text/html",
    "application/xhtml+xml",
    # markdown files
    "text/markdown",
    "application/markdown",
    "application/x-markdown",
    # outlook msg files
    "application/vnd.ms-outlook",
    # images
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/vnd.oasis.opendocument.text",
]
