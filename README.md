[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](./LICENSE.txt)
[![Latest Release](https://img.shields.io/github/v/release/gontazaka/ublock?include_prereleases&label=Release)](https://github.com/gontazaka/uBlock/releases)

***

<h1 align="center">
<sub>
<img  src="./src/img/ublock.svg" height="38" width="38">
</sub>
uBlock 🦆 (uBlock Origin - experimental fork)
</h1>

## License

[GPLv3](./LICENSE.txt). Original Licensor <https://github.com/gorhill/uBlock>  

***

## フォーク元からの変更点

### 🦆 回線速度に応じた`no-large-media`適用切り替え

**(Chromium only)**  
[Navigator.connection](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/connection) を参照して「xx KBより大きいメディア要素をブロックする」の適用を動的に切り替える。※ダッシュボードでの設定はONしておく必要がある

備考：ブラウザーからの情報変化イベント([onchange](https://developer.mozilla.org/en-US/docs/Web/API/NetworkInformation/onchange))で切り替えるため、特に安定しない通信回線ではページ読込中に変化する可能性がある(?)。  
ポップアップに状態表示(`navigator.connection.effectiveType`)しており、値が「4g」では非適用、それ以外は適用としている。＜[仕様](https://wicg.github.io/netinfo/#dfn-effective-connection-type)。ただしブラウザー実装が仕様に従っているか不明＞
![Popup Screenshot](./doc/img/effectiveyype.png)

常時適用（フォーク元同様）させるには`chrome://flags/#force-effective-connection-type`を「3g」などにすればよい。ただしこの情報を使うWEBサービスや拡張機能に影響する。  

### 🦆 ftpスキーム判定削除

Chrome, Firefoxとも現最新バージョンではFTPサポートが削除されているのでURI判定からftp/ftpsスキームを削除。  
コミット https://github.com/gontazaka/uBlock/commit/c4f7c9ae8b793cea705659b4c51a5a576b542beb

### 🦆 ビルトインフィルター非同梱

*uBlock filters*や*EasyList*などのフィルターをパッケージに同梱しない。  
パッケージサイズが1MB以上小さくなるため拡張機能をアップデートして使うメリットが出る。新規インストール時にルール数0となるが「今すぐ更新」すれば最新ルールが普通にダウンロードされる。  

### 🦆 ダークモード微修正

`Advanced settings` > `uiTheme:dark` のデザインが放置されたままなので少し手を加える。  
フォーク元同様にベースは[Mozillaのガイドライン](https://protocol.mozilla.org/fundamentals/color.html)に沿った色定義にしている。  
![Dark Mode Screenshot](./doc/img/dark-settings_3pf.webp)  

### 🦆 セルフホスト

GitHubのリリースでパッケージをセルフホスト([Chromium](https://docs.microsoft.com/ja-jp/deployedge/microsoft-edge-manage-extensions-webstore#distribute-a-privately-hosted-extension), [Firefox](https://extensionworkshop.com/documentation/publish/self-distribution/))している。  
リリース時のGitHub Actionsでアップデート用メタデータ[Chromium](https://github.com/gontazaka/uBlock/blob/meta/chromium/update.xml), [Firefox](https://github.com/gontazaka/uBlock/blob/meta/firefox/updates.json))も更新し`.crx`は鍵付きでパッキング、`.xpi`は[`addons.mozilla.org(AMO)`](https://addons.mozilla.org/firefox/)で署名されるため自動更新対応している。  
※FirefoxのセルフホストはuBlock Originでも行っており、ローカル実行からGitHub Actionsで実行するように変更した点が異なる

セキュリティ都合のためかEdge(Chromium)は初期状態では野良拡張機能はブロックされているためおまじないが必要。  

#### Windows
レジストリ変更（or ポリシーエディタ）  

##### [Microsoft Edge](https://docs.microsoft.com/deployedge/microsoft-edge-policies#extensioninstallallowlist)
例  
```
[HKEY_CURRENT_USER\SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallAllowlist]
"1"="heijcalefhbbecnlkmkmgohkkfmhhhnm"
```

##### [Google Chrome](https://cloud.google.com/docs/chrome-enterprise/policies?policy=ExtensionInstallAllowlist)
Chromeはデフォルトですべての拡張機能が許可。  

***
