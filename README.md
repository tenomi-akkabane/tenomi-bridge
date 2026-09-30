# tenomi-bridge

TENOMI（ことばのいらない AI ロボット）の構成要素のひとつで、Raspberry Pi 上で常駐して動く中継サービスです。

ジェスチャーを認識する Motion Detector（STM32N6570-DK）と、走行する Rover（micro:bit v2）の間をつなぎます。Motion Detectorの出力は USB シリアル、Rover の入力は Bluetooth Low Energy（BLE）で、形式が違うため直接はつながりません。tenomi-bridge がこの 2 つを橋渡しします。

## 構成

```
[Motion Detector]  ジェスチャー認識
      │  USB シリアル："motion: come_here" などの 1 行
      ▼
[tenomi-bridge]  Raspberry Pi 上の常駐サービス（本リポジトリ）
      │  BLE（Nordic UART Service）：Rover 用の JSON 1 行
      ▼
[Rover]  micro:bit v2 ＋ モータ
```

## しくみ

tenomi-bridge が行うのは次の 3 つです。

1. Motion Detectorから USB シリアルで届く行のうち、`motion: <名前>` の行だけを読み取ります。それ以外の行（手のランドマークのデータなど）は読み捨て、無線には流しません。
2. ジェスチャーの名前を、Rover が実行できる走行指令（JSON）に変換します。
3. BLE の Nordic UART Service（NUS）で Rover へ送ります。Rover の探索・接続・切断時の再接続も自動で行います。

| Motion Detectorの出力 | 意味 | Rover へ送る JSON |
|-----------------|------|-------------------|
| `motion: come_here` | 前進 | `{"type":"drive","left":50,"right":50,"duration":2}` |
| `motion: go_away` | 後退 | `{"type":"drive","left":-50,"right":-50,"duration":2}` |
| `motion: right` | 右折 | `{"type":"drive","left":50,"right":25,"duration":2}` |
| `motion: left` | 左折 | `{"type":"drive","left":25,"right":50,"duration":2}` |
| `motion: stop` | 停止 | `{"type":"stop"}` |

走行指令が短い間隔で続いたときは、直前の送信から 1.5 秒経つまで次の走行指令を見送ります（`config.toml` の `cooldown_ms` で変更できます）。`stop` だけは見送らず、常にすぐ送ります。

Raspberry Pi の起動時には systemd がサービスを自動で立ち上げ、プロセスが異常終了したときも再起動します。利用者が行う操作は、ケーブルの接続と電源投入だけです。

## 必要なもの

- 内蔵 Bluetooth と USB ポートを備えた Raspberry Pi
- Raspberry Pi OS 64-bit（Bookworm）、Python 3.11 以上
- Motion Detectorと Raspberry Pi をつなぐ USB ケーブル
- NUS でアドバタイズする Rover（micro:bit v2）

USB 3.0 ポートを持つ機種（Raspberry Pi 4 / 5）では、USB 3.0 と Bluetooth（2.4 GHz）が干渉することがあります。Motion Detectorは USB 2.0 ポート（黒いコネクタ）へ接続してください。機種ごとの動作確認の状況は [INSTALL.md](INSTALL.md) を参照してください。

## 導入の流れ

### 1. ZIP をダウンロードする

PC でこのリポジトリの ZIP をダウンロードします。GitHub のページで **Code → Download ZIP** を選ぶか、次の URL から取得してください。ファイル名は `tenomi-bridge-main.zip` になります。

```
https://github.com/tenomi-akkabane/tenomi-bridge/archive/refs/heads/main.zip
```

### 2. Raspberry Pi へ転送する

ZIP を Raspberry Pi へコピーします。SSH が使える場合は、PC から `scp` で送れます（ユーザ名とホスト名は環境に合わせて読み替えてください）。

```bash
scp tenomi-bridge-main.zip pi@raspberrypi.local:~/
```

USB メモリ経由でコピーしても構いません。

### 3. INSTALL.md に従ってインストールする

ここから先は Raspberry Pi 上での作業です。手順は [INSTALL.md](INSTALL.md) に従ってください。おおまかな流れは次のとおりです。

1. **前提の確認** — ユーザがグループ `dialout` に入っていること、`bluetoothctl show` が `Powered: yes` であること（INSTALL.md §1）
2. **展開** — `unzip tenomi-bridge-main.zip` で展開し、`tenomi-bridge-main/` へ移動（§2）
3. **設定** — `config.example.toml` を `config.toml` にコピー。多くの環境ではこのままで動作します（§3）
4. **インストール** — `bash deploy/install.sh` で Python 仮想環境を作成（§4）
5. **動作確認** — Rover の電源を入れ、Motion Detectorを接続したうえで `tenomi-bridge --config config.toml` を手動で起動し、接続を確認（§5）
6. **常駐化** — `bash deploy/install.sh --enable` で systemd に登録。以後は Raspberry Pi の起動時に自動で動きます（§6）

更新・削除の手順とトラブルシュートも INSTALL.md にあります（§7・§8）。

## 設定

設定は展開したディレクトリの `config.toml` に書きます。変更が必要になり得るのは次の 2 項目だけです。

| 設定 | 既定値 | 変更が必要な場合 |
|------|--------|------------------|
| `[ble] name` | `micro:bit2_UART` | Rover のアドバタイズ名が異なるとき |
| `[serial] port` | `/dev/ttyACM0` | Motion Detectorが別のデバイスパスに見えるとき |

## 稼働状況の確認

常駐化したあとは、systemd とログで状態を確認できます。

```bash
systemctl status tenomi-bridge --no-pager
journalctl -u tenomi-bridge --since "1 hour ago" | grep metrics
```

`metrics` の行には、BLE の接続状態（`ble=up` / `down`）、接続・切断の回数、Rover への送信の成功数などが一定間隔で出力されます。

## ディレクトリ構成

```
tenomi-bridge/
├── src/                          Python パッケージ（tenomi_bridge）
│   ├── main.py                   起動と全体の流れ
│   ├── serial_bridge.py          Motion Detectorからの USB シリアル受信
│   ├── protocol.py               motion: の読み取り、JSON への変換、送信間隔の制御
│   ├── nus_central.py            BLE（NUS）での Rover の探索・接続・送信
│   ├── config.py                 config.toml の読み込み
│   └── metrics.py                稼働状況の集計
├── deploy/
│   ├── install.sh                インストールと systemd への登録
│   └── tenomi-bridge.service.in  systemd ユニットの雛形
├── config.example.toml           設定の雛形
├── INSTALL.md                    インストール手順
├── pyproject.toml
└── requirements.txt
```

## 関連リポジトリ

| リポジトリ | 内容 |
|------------|------|
| [tenomi-motion](https://github.com/tenomi-akkabane/tenomi-motion) | Motion Detector側（ジェスチャー認識） |
| [tenomi-bridge](https://github.com/tenomi-akkabane/tenomi-bridge) | 本リポジトリ |
| [tenomi-rover](https://github.com/tenomi-akkabane/tenomi-rover) | Rover 側（micro:bit v2） |

## ライセンス

Copyright 2026 tenomi-akkabane

[Apache License 2.0](LICENSE) で提供します。実行時に使用する第三者ソフトウェアと商標については [NOTICE.md](NOTICE.md) を参照してください。
