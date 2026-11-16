# Upstream Sync & Release Guidelines

## リポジトリ概要
このリポジトリは `https://github.com/gorhill/uBlock` の独自改造を施したフォーク版。
このフォークの存在意義は以下の独自機能・独自運用にある:
- セルフホスト配布: GitHub Releases で .crx(鍵付き)/.xpi(AMO署名)を配布し、 meta ブランチに自動更新メタデータ(chromium/update.xml, firefox/updates.json)を配置。 拡張機能は個人利用目的で AMO の unlisted(self-distributed)チャンネルで署名する。
- 独自ブランド: 拡張機能名「uBlock 🦆」、Firefox 拡張ID ublock@gontazaka、Chromium 用秘密鍵。
- 独自機能: 回線速度に応じた no-large-media 切替(vAPI.connection)、ロガーのクリックコピー、 フィルターの非同梱(パッケージ軽量化)、locale の minify、ハードリンクによるビルド高速化 など。

## 制約
- origin: ローカル操作(commit/tag)は可。master への Merge は PR 必須。
  - エージェントは作業ブランチの push と PR 作成まで行い、**PR のマージ・タグ作成/push はユーザーが行う**。
- upstream: 一切の変更操作を行わない。fetch のみ（push URL を無効化しておく）。

## マージおよびコンフリクト解決ルール
- アップストリーム（フォーク元）から最新Releaseタグを探し、そのReleaseコミットまでをマージ
- アップストリームの最新Releaseタグを取り込む際は、当リポジトリ固有の改造内容を優先
- マージ後は必ず[ビルドコマンド](#ビルド)と[テストコマンド](#テスト)を実行し、すべてパスすることを確認する

### フォーク維持型マージ
フォークの独自性(ブランド・セルフホスト・独自機能)を軸に、upstream からは機能改善と必須要件のみを取り込む。コンフリクトは 1 件ずつ意図を確認して解消。
- Pros: フォークの存在意義を完全維持。個人利用の署名運用を復旧
- Cons: 手動解消の判断コストが高い。upstream の一部独自最適化(uBOLite/MV3)は取り込まない

### 手順
```bash
# 0. upstream リモート（初回のみ。push は無効化）
git remote add upstream https://github.com/gorhill/uBlock.git
git remote set-url --push upstream DISABLED
git fetch upstream --tags

# 1. 最新の安定版 Release タグを特定（b/rc 等のプレリリースは対象外）
gh release list -R gorhill/uBlock --exclude-pre-releases -L 1
#   gh が使えない場合: 安定版タグ形式 ^[0-9]+\.[0-9]+\.[0-9]+$ の最大値
git tag --sort=-v:refname | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | head -n 1
#   当フォークの現行版（dist/versiongz）より新しくなければ作業不要

# 2. 事前にコンフリクトを確認（作業ツリーは変更されない）
git merge-tree --write-tree --name-only master X.Y.Z

# 3. 作業ブランチでマージ
git switch -c merge/upstream-X.Y.Z master
git merge --no-ff X.Y.Z -m "Merge tag 'X.Y.Z'"
#    コンフリクト解消 → git add → git commit --no-edit

# 4. バージョン更新（別コミット）
printf 'X.Y.Z.0\n' > dist/versiongz
git commit -am "X.Y.Z.0"

# 5. ビルド・テスト（後述）

# 6. push と PR 作成（タグは作らない）
git push -u origin merge/upstream-X.Y.Z
gh pr create -R gontazaka/uBlock --base master --head merge/upstream-X.Y.Z \
  --title "Merge upstream X.Y.Z (X.Y.Z.0)" --body-file <PR本文>
```

### 既知のコンフリクトと解消方針
| ファイル | 原因 | 解消方針 |
|---|---|---|
| `dist/version` | 末尾改行の有無の差で毎回コンフリクトする | upstream の値を採用する（`git checkout --theirs dist/version`） |
| `platform/*/manifest.json` | フォーク独自のブランド・ID・author | 名前・`gecko.id`・author・update_url などフォーク独自の値は残し、upstream の permissions や `strict_min_version` などの変更は取り込む |
| `.github/workflows/*`, `tools/make-*.sh`, `dist/firefox/*`, `dist/chromium/*` | セルフホスト配布・ビルドの独自改造 | フォーク側を優先する。upstream の変更は内容を確認したうえで必要なものだけ手で取り込む |
| `tools/make-assets.sh` | フィルターを同梱しない改造（`exit 0`） | フォーク側を優先する。新しく同梱必須になった資産（例: publicsuffix）があれば `exit 0` より前に追加する。4 桁バージョンは `devbuild` 判定で `assets.dev.json` を読むため、`dist/versiongz` の桁数に応じて `assets.json` / `assets.dev.json` を残す |

### upstream 差分レビューの観点
`git diff --stat <前回タグ> X.Y.Z` を確認し、次の箇所に変更がある場合はフォーク独自部分への影響を個別に確認する。
- `platform/*/manifest.json`（permissions・最小バージョン）
- `platform/*/vapi-*.js`（vAPI.connection などの独自機能）
- `tools/make-*.sh`, `tools/copy-common-files.sh`（ハードリンク・locale minify）
- `assets/assets.json` / `assets/assets.dev.json`（フィルターを同梱しない前提で、オンライン取得の URL が有効か）
- `src/js/logger-ui*.js`（ロガーのクリックコピー）

## バージョニング規則
- フォーク元の Release タグが `X.Y.Z`（`v` は付かない。例: `1.76.2`）の場合、当リポジトリのバージョンは `X.Y.Z.0` とする（例: `1.76.2.0`）
- 同じ upstream 版の上でフォーク独自の修正をリリースする場合は、4 桁目を上げる（例: `1.72.2.3` → `1.72.2.4`）
- バージョン更新時は `dist/versiongz` を書き換えてコミットする（ビルドスクリプトと署名スクリプトはこのファイルを参照する）。`dist/version` は upstream の値のまま変更しない
- 4 桁バージョンの Chromium ビルドは、`tools/make-chromium-meta.py` によって名前に「development build」が付く（既存の仕様）
- タグ `X.Y.Z.0` は **PR のマージ後に、ユーザーが master 上で作成して push する**

> [!CAUTION]
> `.github/workflows/main.yml` はタグが作成されたとき（`on: create`）に動き、GitHub Release の作成・AMO 署名・meta ブランチへのデプロイまで自動で行う。タグの push はリリース作業そのものなので、エージェントは行わない。

## ビルド
```bash
# 準備（初回のみ）
test -d dist/build/uAssets || tools/pull-assets.sh   # publicsuffix 等の取得元
npm ci
# ビルド（Makefile のターゲット名は uBlock0.* のままなので、スクリプトを直接実行する）
tools/make-firefox.sh X.Y.Z.0    # => dist/build/uBlock🦆_X.Y.Z.0.firefox.xpi, dist/build/uBlock🦆.firefox/
tools/make-chromium.sh all       # => dist/build/uBlock🦆.chromium/（~/private-key.pem がなければ .crx は作られない。ローカルではそれで正常）
```

## テスト

### Lint
```bash
npm run lint
```
- upstream の Release タグ時点でも、`no-undef`（`browser` / `chrome`）などのエラーがもともと出る。**判定基準は「upstream の X.Y.Z と比べてエラー件数が増えていないこと」**とする。
  - 比較方法: `git worktree add --detach /tmp/wt X.Y.Z && ln -s $PWD/node_modules /tmp/wt/ && (cd /tmp/wt && npm run lint | tail -2); git worktree remove --force /tmp/wt`

### Firefox一時プロファイルでの拡張機能ロード・広告ブロック検証
Python の selenium (webdriver.Firefox) を用いた自動検証スクリプト `test_firefox_adblock.py` を作成・実行する。スクリプトは**リポジトリ外**（エージェントのアーティファクトディレクトリの `scratch/`）に置き、`git status` を汚さない。

#### 環境準備（sudo 不要、ユーザー領域に導入）
```bash
mkdir -p ~/.local/opt ~/.local/bin
curl -sSL "https://download.mozilla.org/?product=firefox-latest-ssl&os=linux64&lang=en-US" | tar xJ -C ~/.local/opt
GV=$(curl -sSL https://api.github.com/repos/mozilla/geckodriver/releases/latest | python3 -c 'import sys,json;print(json.load(sys.stdin)["tag_name"])')
curl -sSL "https://github.com/mozilla/geckodriver/releases/download/$GV/geckodriver-$GV-linux64.tar.gz" | tar xz -C ~/.local/bin
python3 -m venv ~/.venvs/selenium && ~/.venvs/selenium/bin/pip install selenium
```
- リモートエージェントの VM では、TLS を検査するプロキシ（`HTTPS_PROXY`）を経由して通信する。Firefox は独自の証明書ストアを使うため、プロキシの CA を Firefox enterprise policy（`<firefox>/distribution/policies.json` の `Certificates.Install`）で登録し、プロキシを Firefox の設定（`network.proxy.*`）で指定する。
- 最近の Firefox では、WebDriver から `moz-extension://` へ直接移動することが禁止されている。geckodriver を `--allow-system-access` 付きで起動し、chrome コンテキストから `gBrowser.selectedBrowser.loadURI(...)` で開く。拡張の UUID は pref `extensions.webextensions.uuids` で固定する。

#### 検証内容
1. **一時プロファイルの起動とアドオンの一時インストール**
   - `webdriver.Firefox` を起動（自動的にクリーンな一時プロファイルが生成され、テスト終了時に削除される）。
   - `driver.install_addon("dist/build/uBlock🦆_X.Y.Z.0.firefox.xpi", temporary=True)` により、`uBlock 🦆 X.Y.Z.0` を一時アドオンとしてロードする（Selenium 4.5x では deprecated の警告が出るが、`temporary=True` を使えるのはこの API だけ）。
2. **初回フィルターリスト取得・コンパイル完了の待機**
   - 当フォークはパッケージ軽量化のためフィルターリストをパッケージに同梱せず、起動時にオンライン取得する仕様（[make-assets.sh](tools/make-assets.sh)）となる。
   - `3p-filters.html` 上で `vAPI.messaging.send('dashboard', {what: 'getLists'})` をポーリングし、次の条件がそろうまで待機する（上限 300 秒）: `isUpdating === false`、`netFilterCount` が十分大きい、`user-filters` を除く有効なリストすべてに `cache[*].writeTime` がある。
3. **広告ブロック動作の検証**
   - **外部広告ブロックテストサイト (`https://blockads.fivefilters.org/`)**:
     - FiveFilters の広告ブロックテストページを開き、「Ad blocking enabled!」と判定されることを確認する。
     - CAPTCHA や bot 判定がかかっている場合は**回避せずに**報告し、次項の直接検証の結果を根拠とする。
   - **ネットワークブロック・コスメティックフィルタリングの直接検証**（`https://example.com/` 上で検証。`127.0.0.1` では汎用コスメティックフィルタが無効なため）:
     - ネットワーク層で遮断される広告リクエスト（例: `https://cdn.taboola.com/libtrc/unip/1/tfa.js`。`adsbygoogle.js` 等はローカルシムへリダイレクトされるため `fetch` が成功扱いになる点に注意）が失敗すること。比較用に `https://example.com/` は成功すること。
     - 広告用 DOM 要素（`.ad-banner-box`, `.ad-banner-300x250` 等の現行 EasyList 汎用セレクタ）がコスメティックフィルタによって非表示（`display: none`）になり、比較用の要素は表示されたままであること。
   - 検証結果のスクリーンショットをアーティファクトディレクトリへ保存し、Walkthrough に添付する。

### Verification Plan

#### Automated Verification
- `dist/build/uBlock🦆.firefox/manifest.json` の `version` が `"X.Y.Z.0"`、`browser_specific_settings.gecko.id` が `"ublock@gontazaka"`、`name` が `"uBlock 🦆"`、`permissions` に `"publicSuffix"` が含まれていることを確認する。
- `dist/build/uBlock🦆.chromium/manifest.json` の `version` が `"X.Y.Z.0"` であることを確認する。
- `npm run lint` のエラー件数が upstream の X.Y.Z 以下であることを確認する。
- `~/.venvs/selenium/bin/python <artifact>/scratch/test_firefox_adblock.py "dist/build/uBlock🦆_X.Y.Z.0.firefox.xpi" --out <artifact>` を実行し、すべての検証項目（アドオンロード、フィルターリスト初期化、FiveFilters テスト合格、広告ネットワークリクエスト遮断・DOM要素非表示）が PASS することを確認する。
- テストの前後で `git status -sb` を実行し、作業ツリーとステージングの状態が変わっていないことを確認する。

#### PR 作成後（ユーザー）
- PR をレビューして master へマージする。
- master 上で `git tag X.Y.Z.0 && git push origin X.Y.Z.0` を実行し、CI（`.github/workflows/main.yml`）による Release 作成・AMO 署名申請・meta ブランチ更新を確認する。
- AMO の署名審査に数時間〜数日かかる場合は、12時間ごとに定期実行される `.github/workflows/firefox-signing-poll.yml`（または Actions タブからの手動実行 `Firefox signing poll`）が承認完了を検知し、Release アセットの差し替え（`.firefox.xpi` → `.firefox.signed.xpi`）および `meta` ブランチの `firefox/updates.json` 更新を自動で行う。

