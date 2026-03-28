import { useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Rectangle, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Leafletのデフォルトアイコンを修正
import icon from 'leaflet/dist/images/marker-icon.png'
import iconShadow from 'leaflet/dist/images/marker-shadow.png'

const DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
})

L.Marker.prototype.options.icon = DefaultIcon

interface Point {
  name: string
  lat: number
  lon: number
  input_height: number
  output_height: number
}

interface ResultMapProps {
  points: Point[]
}

// 地図の表示範囲を自動調整するコンポーネント
function FitBounds({ bounds }: { bounds: L.LatLngBoundsExpression }) {
  const map = useMap()

  useEffect(() => {
    map.fitBounds(bounds, { padding: [50, 50] })
  }, [map, bounds])

  return null
}

export function ResultMap({ points }: ResultMapProps) {
  // 範囲を計算
  const { bounds, center } = useMemo(() => {
    if (points.length === 0) {
      return {
        bounds: [[35.6, 139.6], [35.8, 139.9]] as L.LatLngBoundsExpression,
        center: [35.7, 139.75] as [number, number]
      }
    }

    const lats = points.map(p => p.lat)
    const lons = points.map(p => p.lon)

    const minLat = Math.min(...lats)
    const maxLat = Math.max(...lats)
    const minLon = Math.min(...lons)
    const maxLon = Math.max(...lons)

    // バウンディングボックスを少し広げる
    const latPadding = Math.max((maxLat - minLat) * 0.1, 0.001)
    const lonPadding = Math.max((maxLon - minLon) * 0.1, 0.001)

    return {
      bounds: [
        [minLat - latPadding, minLon - lonPadding],
        [maxLat + latPadding, maxLon + lonPadding]
      ] as L.LatLngBoundsExpression,
      center: [(minLat + maxLat) / 2, (minLon + maxLon) / 2] as [number, number]
    }
  }, [points])

  // バウンディングボックス（長方形）の座標
  const rectangleBounds = useMemo(() => {
    if (points.length < 2) return null

    const lats = points.map(p => p.lat)
    const lons = points.map(p => p.lon)

    return [
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)]
    ] as L.LatLngBoundsExpression
  }, [points])

  return (
    <div className="map-container">
      <MapContainer
        center={center}
        zoom={13}
        style={{ height: '300px', width: '100%' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <FitBounds bounds={bounds} />

        {/* バウンディングボックス */}
        {rectangleBounds && (
          <Rectangle
            bounds={rectangleBounds}
            pathOptions={{
              color: '#007bff',
              weight: 2,
              fillColor: '#007bff',
              fillOpacity: 0.1
            }}
          />
        )}

        {/* 各点のマーカー */}
        {points.map((point, index) => (
          <Marker key={index} position={[point.lat, point.lon]}>
            <Popup>
              <strong>{point.name}</strong><br />
              緯度: {point.lat.toFixed(8)}<br />
              経度: {point.lon.toFixed(8)}<br />
              入力高: {point.input_height.toFixed(4)}m<br />
              出力高: {point.output_height.toFixed(4)}m
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}
