#!/usr/bin/env bash
#
# This script assumes a linux environment

set -e

DES=$1/assets

echo "*** Packaging assets in $DES... "

rm -rf $DES
cp -Rl ./assets $DES/

### built-in filters do not include in package
exit 0

mkdir $DES/thirdparties

git submodule update --depth 1 --init
UASSETS=submodules/uAssets

cp -Rl $UASSETS/thirdparties/easylist-downloads.adblockplus.org $DES/thirdparties/
cp -Rl $UASSETS/thirdparties/pgl.yoyo.org                       $DES/thirdparties/
cp -Rl $UASSETS/thirdparties/publicsuffix.org                   $DES/thirdparties/
cp -Rl $UASSETS/thirdparties/urlhaus-filter                     $DES/thirdparties/

mkdir $DES/ublock
cp -Rl $UASSETS/filters/* $DES/ublock/
# Optional filter lists: do not include in package
rm    $DES/ublock/annoyances.txt
