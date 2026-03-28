"""
変換精度検証テスト
"""
import sys
from pathlib import Path

# バックエンドモジュールをインポート
sys.path.insert(0, str(Path(__file__).parent))

from geoid_loader import GeoidManager
from coordinate import latlon_to_plane, plane_to_latlon

BASE_PATH = Path(__file__).parent.parent


def test_geoid_loader():
    """ジオイドデータ読み込みテスト"""
    print("=" * 50)
    print("ジオイドデータ読み込みテスト")
    print("=" * 50)

    manager = GeoidManager(BASE_PATH)

    # 東京駅付近 (35.681236, 139.767125)
    lat, lon = 35.681236, 139.767125

    print(f"\nテスト地点: 東京駅付近")
    print(f"緯度: {lat}, 経度: {lon}")

    g2024 = manager.get_geoid2024_height(lat, lon)
    g2024_island = manager.get_geoid2024_height(lat, lon, use_island_correction=True)
    g2011 = manager.get_geoid2011_height(lat, lon)

    print(f"\nジオイド2024高: {g2024:.4f} m" if g2024 else "ジオイド2024高: 取得失敗")
    print(f"ジオイド2024高(離島補正): {g2024_island:.4f} m" if g2024_island else "ジオイド2024高(離島補正): 取得失敗")
    print(f"ジオイド2011高: {g2011:.4f} m" if g2011 else "ジオイド2011高: 取得失敗")

    if g2024 and g2011:
        print(f"\n2024-2011の差: {g2024 - g2011:.4f} m")

    # 国土地理院の公開値との比較（参考）
    # 東京駅付近のジオイド高は約36m程度
    print("\n※参考: 国土地理院のジオイド計算サービスで確認してください")
    print("  https://vldb.gsi.go.jp/sokuchi/surveycalc/geoid/calcgh/calc_f.html")


def test_coordinate_conversion():
    """座標変換テスト"""
    print("\n" + "=" * 50)
    print("座標変換テスト（平面直角座標 ⇔ 経緯度）")
    print("=" * 50)

    # テストケース: 東京駅付近（9系）
    test_cases = [
        {"name": "東京駅", "lat": 35.681236, "lon": 139.767125, "zone": 9},
        {"name": "大阪駅", "lat": 34.702485, "lon": 135.495951, "zone": 6},
        {"name": "札幌駅", "lat": 43.068661, "lon": 141.350755, "zone": 12},
    ]

    for tc in test_cases:
        print(f"\n--- {tc['name']} ({tc['zone']}系) ---")
        print(f"元の経緯度: ({tc['lat']:.6f}, {tc['lon']:.6f})")

        # 経緯度 → 平面直角座標
        plane = latlon_to_plane(tc['lat'], tc['lon'], tc['zone'])
        print(f"平面直角座標: X={plane.x:.3f} m, Y={plane.y:.3f} m")

        # 平面直角座標 → 経緯度（逆変換）
        latlon = plane_to_latlon(plane.x, plane.y, tc['zone'])
        print(f"逆変換後の経緯度: ({latlon.lat:.6f}, {latlon.lon:.6f})")

        # 誤差計算
        lat_err = abs(tc['lat'] - latlon.lat) * 111000  # 約111km/度
        lon_err = abs(tc['lon'] - latlon.lon) * 111000 * abs(
            __import__('math').cos(__import__('math').radians(tc['lat']))
        )
        print(f"誤差: 緯度方向 {lat_err:.6f} m, 経度方向 {lon_err:.6f} m")


def test_height_conversion():
    """高さ変換テスト"""
    print("\n" + "=" * 50)
    print("高さ変換テスト")
    print("=" * 50)

    manager = GeoidManager(BASE_PATH)

    # 東京駅付近、楕円体高50mと仮定
    lat, lon = 35.681236, 139.767125
    ellipsoid_h = 50.0

    print(f"\nテスト地点: 東京駅付近")
    print(f"緯度: {lat}, 経度: {lon}")
    print(f"入力楕円体高: {ellipsoid_h:.4f} m")

    g2024 = manager.get_geoid2024_height(lat, lon)
    g2011 = manager.get_geoid2011_height(lat, lon)

    if g2024:
        ortho_h_2024 = ellipsoid_h - g2024
        print(f"\nジオイド2024高: {g2024:.4f} m")
        print(f"標高(2024基準): {ortho_h_2024:.4f} m")

    if g2011:
        ortho_h_2011 = ellipsoid_h - g2011
        print(f"\nジオイド2011高: {g2011:.4f} m")
        print(f"標高(2011基準): {ortho_h_2011:.4f} m")

    if g2024 and g2011:
        print(f"\n2024基準と2011基準の標高差: {ortho_h_2024 - ortho_h_2011:.4f} m")


def test_island_detection():
    """離島判定テスト"""
    print("\n" + "=" * 50)
    print("離島判定テスト")
    print("=" * 50)

    manager = GeoidManager(BASE_PATH)

    test_points = [
        {"name": "東京駅", "lat": 35.681236, "lon": 139.767125},
        {"name": "那覇空港", "lat": 26.195810, "lon": 127.645892},
        {"name": "石垣島", "lat": 24.340556, "lon": 124.155833},
        {"name": "父島", "lat": 27.091667, "lon": 142.191667},
    ]

    for p in test_points:
        island = manager.check_island(p['lat'], p['lon'])
        if island:
            print(f"{p['name']}: 離島地域 ({island})")
        else:
            print(f"{p['name']}: 本土")


if __name__ == "__main__":
    test_geoid_loader()
    test_coordinate_conversion()
    test_height_conversion()
    test_island_detection()

    print("\n" + "=" * 50)
    print("テスト完了")
    print("=" * 50)
