#!/usr/bin/env bash

# Source: https://stackoverflow.com/questions/18693962/pack-chrome-extension-on-server-with-only-command-line-interface
# Purpose: Pack a Chromium extension directory into crx format

if test $# -lt 2; then
  echo "Usage: make-chromium-pack.sh <extension dir> <pem path> <output dir[option]>"
  exit 1
fi

dir=$1
key=$2
name=$(basename "$dir")
crx="$name.crx"
pub="$name.pub"
sig="$name.sig"
zip="$name.zip"
tosign="$name.presig"
binary_crx_id="$name.crxid"
trap 'rm -f "$pub" "$sig" "$zip" "$tosign" "$binary_crx_id"' EXIT

if [ -n "$3" ]; then
  output=$3/$crx
else
  output=$crx
fi


# zip up the crx dir
cwd=$(pwd -P)
(cd "$dir" && zip -qr -9 -X "$cwd/$zip" .)


#extract crx id
openssl rsa -in "$key" -pubout -outform der | openssl dgst -sha256 -binary -out "$binary_crx_id"
truncate -s 16 "$binary_crx_id"

#generate file to sign
(
  # echo "$crmagic_hex $version_hex $header_length $pub_len_hex $sig_len_hex"
  printf "CRX3 SignedData"
  echo "00 12 00 00 00 0A 10" | xxd -r -p
  cat "$binary_crx_id" "$zip"
) > "$tosign"

# signature
openssl dgst -sha256 -binary -sign "$key" < "$tosign" > "$sig"

# public key
openssl rsa -pubout -outform DER < "$key" > "$pub" 2>/dev/null


crmagic_hex="43 72 32 34" # Cr24
version_hex="03 00 00 00" # 3
header_length="45 02 00 00"
header_chunk_1="12 AC 04 0A A6 02"
header_chunk_2="12 80 02"
header_chunk_3="82 F1 04 12 0A 10"
(
  echo "$crmagic_hex $version_hex $header_length $header_chunk_1" | xxd -r -p
  cat "$pub"
  echo "$header_chunk_2" | xxd -r -p
  cat "$sig"
  echo "$header_chunk_3" | xxd -r -p
  cat "$binary_crx_id" "$zip"
) > "$output"
echo "Wrote $output"
