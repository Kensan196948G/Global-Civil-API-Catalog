# 運用メモ

## Web UI

- URL: `http://192.168.0.185:49231`
- 固定ポート: `49231`
- ポート定義: `deploy/PORT.lock`
- systemdユーザーサービス: `global-civil-api-catalog-web.service`
- Dockerコンテナ名: `global-civil-api-catalog-web`
- Dockerイメージ名: `global-civil-api-catalog-web:local`

このサービスでは登録済みポート `49231` を変更しません。ホストIPがDHCP等で変わる場合でも、ポート番号は維持します。

## 状態確認

```bash
systemctl --user status global-civil-api-catalog-web.service
docker ps --filter name=global-civil-api-catalog-web
curl http://127.0.0.1:49231/api/health
```

## 再起動

```bash
systemctl --user restart global-civil-api-catalog-web.service
```

## 常駐条件

`loginctl show-user "$USER" -p Linger` が `Linger=yes` のため、ログアウト後もユーザーsystemdサービスは継続します。サービスは `Restart=always` で登録済みです。
