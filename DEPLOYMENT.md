# SLサンプル生成システム デプロイ手順

## 前提条件
- Railwayアカウント
- GitHubアカウント（リポジトリ連携用）
- OpenAI APIキー

## デプロイ手順

### 1. リポジトリ準備

このweb_appフォルダをGitリポジトリとして初期化します:

```bash
cd web_app
git init
git add .
git commit -m "Initial commit: SL Sample Generation System"
```

### 2. GitHubにプッシュ

GitHubで新しいリポジトリを作成し、プッシュします:

```bash
git remote add origin <your-github-repo-url>
git branch -M main
git push -u origin main
```

### 3. Railwayでデプロイ

1. [Railway](https://railway.app/)にログイン
2. "New Project" → "Deploy from GitHub repo"を選択
3. 作成したリポジトリを選択
4. 自動的にビルド・デプロイが開始されます

### 4. 環境変数の設定

Railwayのプロジェクト設定で以下の環境変数を追加:

```
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
```

### 5. Excelファイルのアップロード

**重要**: `米国での業務内容.xlsx`ファイルを親ディレクトリに配置する必要があります。

Railwayの場合:
- リポジトリのルートに`米国での業務内容.xlsx`を配置してコミット
- または、app.pyのパス設定を変更して同じディレクトリに配置

```python
# app.pyの19行目を変更
excel_path = os.path.join(os.path.dirname(__file__), '米国での業務内容.xlsx')
```

### 6. デプロイ確認

1. Railwayが自動生成したURLにアクセス
2. 検索フォームが表示されることを確認
3. デフォルト値（自動車、製造、マネージャー）で検索テスト

## ファイル構成

```
web_app/
├── Procfile              # Railwayデプロイ設定
├── requirements.txt      # Python依存パッケージ
├── .env                 # ローカル環境変数（gitignore対象）
├── .env.example         # 環境変数サンプル
├── .gitignore           # Git除外設定
├── app.py               # メインアプリケーション
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    └── js/main.js
```

## トラブルシューティング

### Excelファイルが見つからない
エラー: `FileNotFoundError: [Errno 2] No such file or directory: '...米国での業務内容.xlsx'`

対処法:
1. Excelファイルをリポジトリに含める（.gitignoreから除外）
2. app.pyのパスを環境に合わせて調整

### OpenAI APIエラー
エラー: `openai.error.AuthenticationError`

対処法:
1. Railway環境変数に正しいAPIキーが設定されているか確認
2. APIキーの有効性を確認

### ポート設定
Railwayは自動的に環境変数`PORT`を設定します。app.pyを以下のように修正する必要がある場合:

```python
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
```

## 本番環境での注意事項

1. `debug=True`を`debug=False`に変更（本番環境では既に推奨設定）
2. OpenAI APIの使用量監視（AI生成は有料）
3. Excel検索の優先実装により、不要なAPI呼び出しを削減
