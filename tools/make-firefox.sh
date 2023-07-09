#!/usr/bin/env bash
#
# This script assumes a linux environment

set -e

echo "*** uBlock🦆.firefox: Creating web store package"

BLDIR=dist/build
DES="$BLDIR"/uBlock🦆.firefox
rm -rf $DES
mkdir -p $DES

echo "*** uBlock🦆.firefox: Copying common files"
bash ./tools/copy-common-files.sh $DES

# Firefox-specific
echo "*** uBlock🦆.firefox: Copying firefox-specific files"
cp    platform/firefox/*.json $DES/
cp -l platform/firefox/*.js   $DES/js/

# Firefox store-specific
cp -Rl $DES/_locales/nb       $DES/_locales/no

# Firefox/webext-specific
rm $DES/img/icon_128.png

echo "*** uBlock🦆.firefox: Generating meta..."
python3 tools/make-firefox-meta.py $DES/

if [ "$1" = all ]; then
    echo "*** uBlock🦆.firefox: Creating package..."
    pushd $DES > /dev/null
    zip ../$(basename $DES).xpi -qr -9 *
    popd > /dev/null
elif [ -n "$1" ]; then
    echo "*** uBlock🦆.firefox: Creating versioned package..."
    pushd $DES > /dev/null
    zip ../$(basename $DES).xpi -qr -9 *
    popd > /dev/null
    mv "$BLDIR"/uBlock🦆.firefox.xpi "$BLDIR"/uBlock🦆_"$1".firefox.xpi
fi

echo "*** uBlock🦆.firefox: Package done."
