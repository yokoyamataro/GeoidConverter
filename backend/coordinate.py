"""
座標変換モジュール
- 平面直角座標系（日本測地系2011）⇔ 経緯度（GRS80楕円体）
"""
import math
from dataclasses import dataclass

# GRS80楕円体パラメータ
GRS80_A = 6378137.0  # 長半径 (m)
GRS80_F = 1 / 298.257222101  # 扁平率
GRS80_E2 = 2 * GRS80_F - GRS80_F ** 2  # 第一離心率の二乗

# 日本の平面直角座標系 原点（系番号1〜19）
# (緯度, 経度) in degrees
PLANE_ORIGINS = {
    1: (33.0, 129.5),           # 長崎県、鹿児島県の一部
    2: (33.0, 131.0),           # 福岡県、佐賀県、熊本県、大分県、宮崎県、鹿児島県
    3: (36.0, 132.166666667),   # 山口県、島根県、広島県
    4: (33.0, 133.5),           # 香川県、愛媛県、徳島県、高知県
    5: (36.0, 134.333333333),   # 兵庫県、鳥取県、岡山県
    6: (36.0, 136.0),           # 京都府、大阪府、福井県、滋賀県、三重県、奈良県、和歌山県
    7: (36.0, 137.166666667),   # 石川県、富山県、岐阜県、愛知県
    8: (36.0, 138.5),           # 新潟県、長野県、山梨県、静岡県
    9: (36.0, 139.833333333),   # 東京都、福島県、栃木県、茨城県、埼玉県、千葉県、群馬県、神奈川県
    10: (40.0, 140.833333333),  # 青森県、秋田県、山形県、岩手県、宮城県
    11: (44.0, 140.25),         # 北海道（西部）
    12: (44.0, 142.25),         # 北海道（中央部）
    13: (44.0, 144.25),         # 北海道（東部）
    14: (26.0, 142.0),          # 東京都の一部（小笠原諸島）
    15: (26.0, 127.5),          # 沖縄県
    16: (26.0, 124.0),          # 沖縄県の一部（先島諸島）
    17: (26.0, 131.0),          # 沖縄県の一部（大東諸島）
    18: (20.0, 136.0),          # 東京都の一部（沖ノ鳥島）
    19: (26.0, 154.0),          # 東京都の一部（南鳥島）
}


@dataclass
class LatLon:
    """緯度経度"""
    lat: float  # 緯度（度）
    lon: float  # 経度（度）


@dataclass
class PlaneXY:
    """平面直角座標"""
    x: float  # X座標（北方向、m）
    y: float  # Y座標（東方向、m）
    zone: int  # 系番号（1〜19）


def deg2rad(deg: float) -> float:
    return deg * math.pi / 180.0


def rad2deg(rad: float) -> float:
    return rad * 180.0 / math.pi


def latlon_to_plane(lat: float, lon: float, zone: int) -> PlaneXY:
    """
    経緯度から平面直角座標へ変換（ガウス・クリューゲル投影）

    Args:
        lat: 緯度（度）
        lon: 経度（度）
        zone: 系番号（1〜19）

    Returns:
        PlaneXY オブジェクト
    """
    if zone not in PLANE_ORIGINS:
        raise ValueError(f"無効な系番号: {zone}")

    lat0, lon0 = PLANE_ORIGINS[zone]

    # ラジアンに変換
    phi = deg2rad(lat)
    lam = deg2rad(lon)
    phi0 = deg2rad(lat0)
    lam0 = deg2rad(lon0)

    # 補助量
    a = GRS80_A
    e2 = GRS80_E2
    e_prime2 = e2 / (1 - e2)  # 第二離心率の二乗

    # 子午線弧長の計算係数
    n = (a - a * (1 - GRS80_F)) / (a + a * (1 - GRS80_F))
    A0 = 1 + n**2 / 4 + n**4 / 64
    A2 = -3/2 * (n - n**3 / 8)
    A4 = 15/16 * (n**2 - n**4 / 4)
    A6 = -35/48 * n**3
    A8 = 315/512 * n**4

    # 子午線弧長
    def meridian_arc(phi):
        return a / (1 + n) * (
            A0 * phi +
            A2 * math.sin(2 * phi) +
            A4 * math.sin(4 * phi) +
            A6 * math.sin(6 * phi) +
            A8 * math.sin(8 * phi)
        )

    M = meridian_arc(phi)
    M0 = meridian_arc(phi0)

    # 計算
    N = a / math.sqrt(1 - e2 * math.sin(phi)**2)
    t = math.tan(phi)
    eta2 = e_prime2 * math.cos(phi)**2
    l = lam - lam0

    # ガウス・クリューゲル座標
    x = (M - M0) + N * t * (
        l**2 / 2 * math.cos(phi)**2 +
        l**4 / 24 * math.cos(phi)**4 * (5 - t**2 + 9*eta2 + 4*eta2**2) +
        l**6 / 720 * math.cos(phi)**6 * (61 - 58*t**2 + t**4 + 270*eta2 - 330*t**2*eta2)
    )

    y = N * (
        l * math.cos(phi) +
        l**3 / 6 * math.cos(phi)**3 * (1 - t**2 + eta2) +
        l**5 / 120 * math.cos(phi)**5 * (5 - 18*t**2 + t**4 + 14*eta2 - 58*t**2*eta2)
    )

    # 縮尺係数 m0 = 0.9999
    m0 = 0.9999
    x *= m0
    y *= m0

    return PlaneXY(x=x, y=y, zone=zone)


def plane_to_latlon(x: float, y: float, zone: int) -> LatLon:
    """
    平面直角座標から経緯度へ変換（逆ガウス・クリューゲル投影）

    Args:
        x: X座標（北方向、m）
        y: Y座標（東方向、m）
        zone: 系番号（1〜19）

    Returns:
        LatLon オブジェクト
    """
    if zone not in PLANE_ORIGINS:
        raise ValueError(f"無効な系番号: {zone}")

    lat0, lon0 = PLANE_ORIGINS[zone]

    # 縮尺係数で補正
    m0 = 0.9999
    x /= m0
    y /= m0

    # ラジアンに変換
    phi0 = deg2rad(lat0)
    lam0 = deg2rad(lon0)

    a = GRS80_A
    e2 = GRS80_E2
    e_prime2 = e2 / (1 - e2)

    # 子午線弧長係数
    n = (a - a * (1 - GRS80_F)) / (a + a * (1 - GRS80_F))
    A0 = 1 + n**2 / 4 + n**4 / 64
    A2 = -3/2 * (n - n**3 / 8)
    A4 = 15/16 * (n**2 - n**4 / 4)
    A6 = -35/48 * n**3
    A8 = 315/512 * n**4

    def meridian_arc(phi):
        return a / (1 + n) * (
            A0 * phi +
            A2 * math.sin(2 * phi) +
            A4 * math.sin(4 * phi) +
            A6 * math.sin(6 * phi) +
            A8 * math.sin(8 * phi)
        )

    M0 = meridian_arc(phi0)
    M = M0 + x

    # フットプリント緯度（Newton-Raphson法）
    phi_f = M / (a * A0 / (1 + n))
    for _ in range(10):
        M_f = meridian_arc(phi_f)
        N_f = a / math.sqrt(1 - e2 * math.sin(phi_f)**2)
        phi_f += (M - M_f) / N_f

    # フットプリント緯度での諸量
    N_f = a / math.sqrt(1 - e2 * math.sin(phi_f)**2)
    t_f = math.tan(phi_f)
    eta2_f = e_prime2 * math.cos(phi_f)**2
    R_f = a * (1 - e2) / (1 - e2 * math.sin(phi_f)**2)**1.5

    # 緯度・経度の計算
    phi = phi_f - t_f / (2 * R_f * N_f) * y**2 * (
        1 -
        y**2 / (12 * N_f**2) * (5 + 3*t_f**2 + eta2_f - 9*eta2_f*t_f**2) +
        y**4 / (360 * N_f**4) * (61 + 90*t_f**2 + 45*t_f**4)
    )

    lam = lam0 + y / (N_f * math.cos(phi_f)) * (
        1 -
        y**2 / (6 * N_f**2) * (1 + 2*t_f**2 + eta2_f) +
        y**4 / (120 * N_f**4) * (5 + 28*t_f**2 + 24*t_f**4 + 6*eta2_f + 8*t_f**2*eta2_f)
    )

    return LatLon(lat=rad2deg(phi), lon=rad2deg(lam))


def get_zone_name(zone: int) -> str:
    """系番号から対象地域の説明を取得"""
    zone_descriptions = {
        1: "長崎県、鹿児島県の一部",
        2: "福岡県、佐賀県、熊本県、大分県、宮崎県、鹿児島県",
        3: "山口県、島根県、広島県",
        4: "香川県、愛媛県、徳島県、高知県",
        5: "兵庫県、鳥取県、岡山県",
        6: "京都府、大阪府、福井県、滋賀県、三重県、奈良県、和歌山県",
        7: "石川県、富山県、岐阜県、愛知県",
        8: "新潟県、長野県、山梨県、静岡県",
        9: "東京都、福島県、栃木県、茨城県、埼玉県、千葉県、群馬県、神奈川県",
        10: "青森県、秋田県、山形県、岩手県、宮城県",
        11: "北海道（西部）",
        12: "北海道（中央部）",
        13: "北海道（東部）",
        14: "小笠原諸島",
        15: "沖縄県（本島）",
        16: "先島諸島",
        17: "大東諸島",
        18: "沖ノ鳥島",
        19: "南鳥島",
    }
    return zone_descriptions.get(zone, "不明")
