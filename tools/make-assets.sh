#!/usr/bin/env bash
#
# This script assumes a linux environment

set -e

DES=$1/assets

echo "*** Packaging assets in $DES... "

rm -rf $DES
cp -Rl ./assets $DES/

mkdir -p $DES/thirdparties

ASSETS_MAIN=dist/build/uAssets/main
ASSETS_PROD=dist/build/uAssets/prod

cp -Rl $ASSETS_MAIN/thirdparties/publicsuffix.org $DES/thirdparties/
### built-in filters do not include in package
exit 0
cp -Rl $ASSETS_MAIN/thirdparties/pgl.yoyo.org     $DES/thirdparties/
cp -Rl $ASSETS_MAIN/thirdparties/urlhaus-filter   $DES/thirdparties/

mkdir -p $DES/ublock
cp $ASSETS_PROD/filters/* $DES/ublock/

# Do not include in package
rm $DES/ublock/annoyances.txt
rm $DES/ublock/lan-block.txt
rm $DES/ublock/ubol-filters.txt
