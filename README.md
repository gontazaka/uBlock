[![GitHub CI](https://github.com/gontazaka/uBlock/actions/workflows/main.yml/badge.svg)](https://github.com/gontazaka/uBlock/actions/workflows/main.yml)
[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://github.com/gorhill/uBlock/blob/master/LICENSE.txt)

*** 

<h1 align="center">
<sub>
<img  src="./src/img/ublock.svg" height="38" width="38">
</sub>
uBlock GZ (uBlock Origin - experimental fork)
</h1>

Original readme : <https://github.com/gorhill/uBlock#readme>

***

## フォーク元からの変更点

### 回線速度に応じた`no-large-media`適用切り替え

**(Chromium only)**  
[Navigator.connection](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/connection) を参照して「xx KBより大きいメディア要素をブロックする」の適用を動的に切り替える。※ダッシュボードでの設定はONしておく必要がある

備考：ブラウザーからの情報変化イベント([onchange](https://developer.mozilla.org/en-US/docs/Web/API/NetworkInformation/onchange))で切り替えるため、特に安定しない通信回線ではページ読込中に変化する可能性がある(?)。  
状態表示は実装していないがDevToolsのConsoleに`navigator.connection.effectiveType`で確認できる値が「4G」では非適用、それ以外は適用としている。

***

## License

[GPLv3](./LICENSE.txt).
