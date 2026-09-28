# NOTICE

tenomi-bridge
Copyright 2026 tenomi-akkabane

本リポジトリのソースコードは Apache License 2.0 で提供します。全文はリポジトリ直下の `LICENSE` を参照してください。

## 実行時に使用する第三者ソフトウェア

本リポジトリには第三者のソースコードを同梱していません。次のパッケージは、`deploy/install.sh` の実行時に pip で PyPI から取得されます。それぞれのライセンスは各パッケージに従います。

| パッケージ | 用途 | ライセンス |
|------------|------|------------|
| [bleak](https://github.com/hbldh/bleak) | Bluetooth Low Energy の通信（BlueZ 経由） | MIT |
| [pyserial](https://github.com/pyserial/pyserial) | USB シリアルの通信 | BSD-3-Clause |

## 商標

Raspberry Pi は Raspberry Pi Ltd の商標です。micro:bit は Micro:bit Educational Foundation の商標です。Bluetooth は Bluetooth SIG, Inc. の登録商標です。STM32 は STMicroelectronics の登録商標です。その他の会社名・製品名は、各社の商標または登録商標です。
