# ジオイド変換ツール (Geoid Converter)

標高・ジオイド高・楕円体高の相互変換を行うWebアプリケーション

## 機能

- **高さ変換**
  - 楕円体高 ⇔ ジオイド2024高（標高）
  - 楕円体高 ⇔ ジオイド2011高（標高）
  - ジオイド2024高 ⇔ ジオイド2011高

- **座標形式**
  - 経緯度（緯度, 経度）
  - 平面直角座標系（系1〜19）

- **入力形式**
  - TSV/CSV形式でデータを貼り付け
  - 形式: `点名, X(緯度), Y(経度), Z(高さ)`

- **離島対応**
  - 離島地域を自動検出
  - Hrefconv2024による離島補正オプション

## 起動方法

### 必要条件
- Python 3.10+
- Node.js 20+

### 起動

```bash
# Windows
start.bat

# または手動で起動

# バックエンド
cd backend
pip install -r requirements.txt
python main.py

# フロントエンド（別ターミナル）
cd frontend
npm install
npm run dev
```

### アクセス
- フロントエンド: http://localhost:5173
- バックエンドAPI: http://localhost:8000

## ジオイドデータ

以下のデータが必要です:

```
GeoidConverter/
├── gsigeoid2024/
│   ├── JPGEO2024.isg              # ジオイド2024（本土用）
│   └── JPGEO2024+Hrefconv2024.isg # ジオイド2024（離島補正込み）
└── gsigeo2011_ver2_2_asc/
    └── program/
        └── gsigeo2011_ver2_2.asc   # ジオイド2011
```

## API

### POST /convert
座標・高さ変換を実行

```json
{
  "points": [{"name": "P1", "x": 35.68, "y": 139.77, "z": 50.0}],
  "input_coord_type": "latlon",
  "input_height_type": "ellipsoid",
  "output_height_type": "geoid2024",
  "zone": null,
  "use_island_correction": false
}
```

### GET /geoid/{lat}/{lon}
指定座標のジオイド高情報を取得
