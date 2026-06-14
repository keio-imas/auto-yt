# auto-yt

流れている音楽をマイク入力から短時間録音し，曲名を認識して，YouTube検索の一番上の動画をブラウザで開きます．
通常実行では監視を続け，曲が切り替わったときだけ新しいYouTube動画を開きます．
ブラウザにはローカルのプレイヤーページを1つだけ開き，曲が変わるたびに同じページ内の動画を差し替えます．

## セットアップ

```bash
uv sync
```

macOSでは初回実行時にマイク権限が必要です．PC内部で再生している音を直接取りたい場合は，BlackHoleなどの仮想オーディオデバイスを入力に設定してください．

## 使い方

```bash
uv run auto-yt
```

既定では `uv run auto-yt --list-devices` で `*` が付いている入力デバイスを使います．

停止する場合は `Ctrl+C` を押してください．
ブラウザで開かれる `http://127.0.0.1:.../` のプレイヤーページは，`auto-yt` 実行中だけ動作します．
YouTube埋め込みで再生できない動画が出た場合は，同じ検索結果の次候補へ自動的に進みます．

1回だけ認識して終了する場合:

```bash
uv run auto-yt --once
```

録音時間を変える場合:

```bash
uv run auto-yt --seconds 12
```

既定の録音時間は `6` 秒です．反応をさらに速くしたい場合:

```bash
uv run auto-yt --seconds 4
```

チェック間隔を変える場合:

```bash
uv run auto-yt --interval 3
```

既定のチェック間隔は `0` 秒です．録音と認識が終わり次第，すぐ次のチェックに入ります．

誤認識による切り替えを減らす場合:

```bash
uv run auto-yt --confirmations 3
```

`--confirmations` は，同じ曲名が何回連続で認識されたら切り替えるかを指定します．既定値は `1` です．精度を優先するなら `2` や `3` を指定してください．

認識結果の言語を指定する場合:

```bash
uv run auto-yt --language ja-JP
```

未指定時はシステムの言語設定を使います。

入力デバイスを確認する場合:

```bash
uv run auto-yt --list-devices
```

`--device-list` も同じ意味で使えます．

入力デバイスを指定する場合:

```bash
uv run auto-yt --device 2
```

入力デバイス名で指定する場合:

```bash
uv run auto-yt --device-name iPhone
```

多入力オーディオインターフェイスで特定chを録る場合:

```bash
uv run auto-yt --device 7 --channels 2
```

`--channels auto` が既定です．入力chが複数あるデバイスを指定した場合は，最大16chまで録音して一番音が大きいchを自動的に使います．
macOSの既定入力デバイスが多入力デバイスの場合も，同じく全chから一番音が大きいchを自動的に使います．

録音された音を確認する場合:

```bash
uv run auto-yt --once --no-open --save-sample sample.wav
```

全入力デバイスを短時間録って音量だけ確認する場合:

```bash
uv run auto-yt --probe-inputs --seconds 3
```

`--sample-rate` は既定で `auto` です．指定デバイスの既定サンプルレートで録音します．

`Audio level` の `peak` が `-55 dBFS` より小さい場合は，ほぼ無音です．macOSでYouTubeやSpotifyなどPC内部の音を認識したい場合，通常のマイクではなくBlackHoleなどの仮想オーディオデバイスを入力に指定してください．オーディオインターフェイスから音が取れない環境では，iPhone Microphoneなど実際に音量が出る入力デバイスを指定してください．

`MacBook Proのマイク` でも `-120 dBFS` になる場合は，macOSのマイク権限が拒否されている可能性が高いです．システム設定の「プライバシーとセキュリティ」から，実行しているターミナルアプリのマイク権限を許可してください．許可後はターミナルアプリを再起動してください．

YouTubeの自動再生はブラウザの自動再生ポリシーに依存します．動画開始を優先するため，埋め込みプレイヤーには `autoplay=1&mute=1` を指定しています．音を出すには，ブラウザ側でミュート解除が必要になる場合があります．

## 注意

- 音楽認識にはインターネット接続が必要です．
- 周囲の音をマイクで拾う方式なので，音量やノイズによって認識精度が変わります．
- YouTubeの検索結果URL取得には `yt-dlp` を使います．

## License

[MIT License](https://choosealicense.com/licenses/mit/)
