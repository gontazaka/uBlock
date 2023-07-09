#!/usr/bin/env bash
#
# This script assumes a linux environment

set -e

echo "*** uBlock🦆.chromium: Creating web store package"

DES=dist/build/uBlock🦆.chromium
PEM=~/private-key.pem
rm -rf $DES
mkdir -p $DES

echo "*** uBlock🦆.chromium: Copying common files"
bash ./tools/copy-common-files.sh $DES

# Chromium-specific
echo "*** uBlock🦆.chromium: Copying chromium-specific files"
cp -l platform/chromium/*.js   $DES/js/
cp -l platform/chromium/*.html $DES/
cp    platform/chromium/*.json $DES/

# Chrome store-specific
cp -Rl $DES/_locales/nb $DES/_locales/no

echo "*** uBlock🦆.chromium: Generating meta..."
python3 tools/make-chromium-meta.py $DES/

if [ "$1" = all ]; then
    echo "*** uBlock🦆.chromium: Creating plain package..."
    # pushd $DES/ > /dev/null
    # zip ../$(basename $DES).zip -qr *
    # popd > /dev/null
    [ -f "$PEM" ] && bash tools/make-chromium-pack.sh $DES $PEM $(readlink -f $(dirname $DES))
elif [ -n "$1" ]; then
    echo "*** uBlock🦆.chromium: Creating versioned package..."
    # pushd $DES/ > /dev/null
    # zip ../uBlock🦆_"$1".chromium.zip -qr *
    # popd > /dev/null
    if [ -f "$PEM" ]; then
        bash tools/make-chromium-pack.sh $DES $PEM $(readlink -f $(dirname $DES))
        pushd $(dirname $DES) > /dev/null
        mv $(basename $DES).crx uBlock🦆_"$1".chromium.crx
        popd > /dev/null
    fi
fi

echo "*** uBlock🦆.chromium: Package done."
