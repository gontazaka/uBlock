#!/usr/bin/env bash
#
# This script assumes a linux environment

set -e

DES=$1

bash ./tools/make-assets.sh         $DES

cp -Rl src/css                      $DES/
cp -Rl src/img                      $DES/
mkdir -p $DES/js
cp -Rl src/js/*.js                  $DES/js/
cp -Rl src/js/codemirror            $DES/js/
cp -Rl src/js/scriptlets            $DES/js/
cp -Rl src/js/wasm                  $DES/js/
cp -Rl src/lib                      $DES/
cp -Rl src/web_accessible_resources $DES/

# minifiy locales
#cp -Rl src/_locales                 $DES/
for srcpath in `find src/_locales -type f -name '*.json'`; do
  dstpath=${DES}/${srcpath#*/}
  mkdir -p $(dirname ${dstpath})
  cat ${srcpath} | jq -c > ${dstpath}
done

cp -l src/*.html                    $DES/
cp -l platform/common/*.js          $DES/js/
cp -l platform/common/*.json        $DES/
cp -l LICENSE.txt                   $DES/

# Remove sources
shopt -s extglob
shopt -s globstar
rm $DES/**/@(*.wat)
