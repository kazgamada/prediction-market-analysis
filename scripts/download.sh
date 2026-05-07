#!/bin/bash
set -e
set -o pipefail

URL="https://s3.jbecker.dev/data.tar.zst"
OUTPUT_FILE="data.tar.zst"
DATA_DIR="data"
DATA_PATH="${DATA_DIR}/${OUTPUT_FILE}"
SENTINEL="${DATA_DIR}/.download_complete"


# Skip if a previous run completed successfully
if [ -f "$SENTINEL" ]; then
    echo "Data already downloaded and extracted, skipping."
    exit 0
fi

if ! command -v zstd &> /dev/null; then
    echo "Error: zstd is required but not installed."
    echo "Run 'make setup' or install zstd manually."
    exit 1
fi

mkdir -p "$DATA_DIR"

# Stream the archive straight into tar to avoid keeping the .zst on disk
# alongside the extracted tree (matters on bounded volumes like Render's
# 10GB persistent disk).
stream_extract() {
    if command -v curl &> /dev/null; then
        echo "Streaming download with curl + zstd | tar..."
        curl -fL --retry 3 --retry-delay 5 "$URL" | zstd -d --stdout | tar -xf -
    elif command -v wget &> /dev/null; then
        echo "Streaming download with wget + zstd | tar..."
        wget -O - "$URL" | zstd -d --stdout | tar -xf -
    else
        echo "Error: curl or wget required for streaming download."
        exit 1
    fi
}

# Two-step path kept for environments with aria2c (faster parallel chunks,
# at the cost of needing room for the .zst on disk).
two_step() {
    echo "Downloading with aria2c..."
    aria2c -x 16 -s 16 -d "$DATA_DIR" -o "$OUTPUT_FILE" "$URL"
    echo "Extracting $OUTPUT_FILE..."
    zstd -d "$DATA_PATH" --stdout | tar -xf -
    rm -f "$DATA_PATH"
}

if command -v aria2c &> /dev/null; then
    two_step
else
    stream_extract
fi

touch "$SENTINEL"
echo "Data directory ready."
