# tenomi-bridge インストール手順（Raspberry Pi）

この文書の対象は **Raspberry Pi** です。Windows や、Raspberry Pi 以外の Linux マシンへの導入は扱いません。動作を確認したのは Raspberry Pi 3 です。Raspberry Pi 4 / 5 でもインストールと運用は可能ですが、未検証です。Raspberry Pi 4 / 5 では USB 3.0 と Bluetooth（2.4 GHz）が干渉することがあるため、制御側の USB シリアルは USB 2.0 ポートへ接続してください。

tenomi-bridge は、Raspberry Pi の内蔵 Bluetooth と USB シリアルを使う常駐サービスです。USB シリアルで受け取った制御指示を、Bluetooth Low Energy の Nordic UART Service（NUS）で Rover（micro:bit）へ転送します。

配布 ZIP を Raspberry Pi にコピーし、この文書の順に進めてください。

---

## 1. 前提


| 項目        | 内容                                                                                                    |
| --------- | ----------------------------------------------------------------------------------------------------- |
| ハードウェア    | 内蔵 Bluetooth 付きの Raspberry Pi。確認済みは Pi 3。Pi 4 / 5 は可（USB 3.0 ポートを避ける）。公式の電源アダプタを使い、電流不足を避けてください       |
| OS        | Raspberry Pi OS 64-bit（Bookworm）。Python 3.11 以上（`python3 --version`）                                  |
| Bluetooth | 内蔵アダプタ。`bluetoothctl show` の出力に `Powered: yes` があること                                                  |
| 権限        | USB シリアル用にグループ `dialout` に入っていること。Bluetooth は下の `bluetoothctl show` で確認します。サービスの登録に管理者権限（`sudo`）が必要です |
| 接続する機器    | 制御側を Pi の USB へ接続します（シリアルの例: `/dev/ttyACM0`）。Rover は NUS でアドバタイズしていること                                |


USB シリアルを使うため、ログインユーザがグループ `dialout` に入っているか確認します。

```bash
groups
```

`groups` の出力に `dialout` が無ければ、`usermod` でユーザをそのグループへ追加します。  
追加したあとは、一度ログアウトして入り直してください。

```bash
sudo usermod -aG dialout "$USER"
# 一度ログアウトして入り直す
```

内蔵 Bluetooth が有効であることを確認します。`Powered: yes` となっていることを確認してください。

```bash
bluetoothctl show
```

手起動で Bluetooth の権限エラーになるときだけ、`usermod` でユーザをグループ `bluetooth` へ追加します。  
追加後は、同様にログインし直してください。

```bash
sudo usermod -aG bluetooth "$USER"
# 一度ログアウトして入り直す
```

---



## 2. 配布物を Raspberry Pi へ

ZIP を Raspberry Pi へコピーし、Pi のシェルで展開します。SSH でも、Pi 本体の端末でも構いません。ファイル名の版は ZIP に合わせて読み替えてください。

```bash
unzip tenomi-bridge-main.zip
cd tenomi-bridge-main
```

インストールに使う主なファイルは、設定の雛形 `config.example.toml` と、導入スクリプト `deploy/install.sh` です。

---



## 3. 設定

雛形をコピーし、内容を確認します。多くの環境では、このままで動作します。

```bash
cp -n config.example.toml config.toml
```

Rover はアドバタイズ名で探します。手元の名前が雛形と違うときだけ、`[ble] name` を書き換えてください。


| キー           | 意味             | 雛形の値              |
| ------------ | -------------- | ----------------- |
| `[ble] name` | Rover のアドバタイズ名 | `micro:bit2_UART` |


シリアル装置が `/dev/ttyACM0` でない場合のみ、`[serial] port` を実機に合わせてください。`[ble] address` は空のままにします。

---



## 4. インストール

展開したディレクトリで、**サービスを動かす一般ユーザ**として実行します。  
Pythonの仮想環境を構築します。しばし時間を要します。  
なお、この段階では常駐サービスの登録は行われません。

```bash
bash deploy/install.sh
```

---



## 5. 動作確認

tenomi-bridge は Bluetooth と USB シリアルの両方を使います。確認の前に、Rover（micro:bit）の電源を入れ、制御側のボードを Pi の USB に接続してください。

シリアルポートが見えることを確認します。

```bash
ls /dev/ttyACM*
```

Python の仮想環境を有効にしたあと、tenomi-bridge を起動します。

```bash
source .venv/bin/activate
tenomi-bridge --config config.toml
```

ログに NUS の接続と、シリアルのオープン（例: `serial open /dev/ttyACM0`）が出れば確認完了です。`could not open port /dev/ttyACM0` が続く場合は、制御側ボードの接続と `[serial] port` を見直してください。確認できたら `Ctrl+C` で止めます。

---



## 6. 常駐化

手起動を止めたあと、サービスとして登録します。登録だけ管理者権限を使います。パスワードを求められたら入力してください。

```bash
bash deploy/install.sh --enable
```

登録できたかを確認します。is-enabled が enabled、status が active であれば成功です。

```bash
systemctl is-enabled tenomi-bridge
systemctl status tenomi-bridge --no-pager
```

再起動のあとでもサービスが起動することを確認します。

```bash
sudo reboot
# 復帰後
systemctl is-active tenomi-bridge
```

常駐したあとも、サービスは展開したディレクトリの `.venv`と `config.toml` を使います。このディレクトリを削除すると、サービスは起動しなくなります。

---



## 7. 更新・削除



### 更新

新しい版に入れ替えるときは、稼働中のサービスを先に止めます。

```bash
sudo systemctl disable --now tenomi-bridge
```

新しい ZIP を **別のディレクトリ** に展開します。旧展開の上書きはしません。旧環境の `config.toml` を利用する場合は、新しい展開ディレクトリへコピーします。

```bash
unzip tenomi-bridge-main.zip -d tenomi-bridge-new   # 旧展開と同じ名前にならないよう、別のディレクトリへ展開
cd tenomi-bridge-new/tenomi-bridge-main   # 新しい展開先
# 必要なら: cp /path/to/old/config.toml ./config.toml
bash deploy/install.sh
```

§5 と同じ手起動で接続を確認し、問題なければ常駐化します。

```bash
bash deploy/install.sh --enable
```

新しいサービスが動いていれば、旧展開ディレクトリは削除して構いません。

### 削除

使わなくなったときは、先にサービスを止めます。

```bash
sudo systemctl disable --now tenomi-bridge
```

systemd の登録を外します。

```bash
sudo rm -f /etc/systemd/system/tenomi-bridge.service
sudo systemctl daemon-reload
```

サービスを止めたあとであれば、展開ディレクトリ（`.venv` と `config.toml` を含む）を Raspberry Pi 上から削除して構いません。常駐したままディレクトリを消すと、サービスは起動できなくなります。

---



## 8. うまくいかないとき


| 症状                                                      | 確認                                                                                  |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `missing pyproject.toml`                                | 展開したディレクトリ（例: `tenomi-bridge-main/`）で `install.sh` を実行しているか                        |
| `run as the Linux user that owns the venv, not as root` | `sudo bash deploy/install.sh` ではなく `bash deploy/install.sh` で実行しているか                |
| `could not open port /dev/ttyACM0`                      | 制御側ボードを USB 接続しているか。`ls /dev/ttyACM*`。ユーザが `dialout` に入っているか                        |
| `ble=down` / `scan_fail`                                | Rover の電源、`config.toml` の `name` がアドバタイズ名と一致しているか、`bluetoothctl show` の結果           |
| 再起動後にサービスが無い                                            | `bash deploy/install.sh --enable` まで実行したか。`systemctl is-enabled tenomi-bridge` が有効か |


