import { useState, useEffect, useRef } from 'react'
import './App.css'
import { ResultMap } from './ResultMap'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

type CoordType = 'latlon' | 'plane'
type HeightType = 'ellipsoid' | 'geoid2024' | 'geoid2011'
type TabType = 'text' | 'las'

interface PointInput {
  name: string
  x: number
  y: number
  z: number
}

interface PointOutput {
  name: string
  lat: number
  lon: number
  input_height: number
  output_height: number
  geoid_height: number | null
  is_island: boolean
  island_region: string | null
  warning: string | null
}

interface ConvertResponse {
  points: PointOutput[]
  has_island_points: boolean
}

interface LASJob {
  job_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  filename: string
  point_count: number
  created_at: string
  expires_at: string
  progress: number
  error: string | null
  stats: {
    total_points: number
    processed_points: number
    failed_points: number
    min_correction: number
    max_correction: number
    avg_correction: number
  } | null
}

interface LASUploadResponse {
  job_id: string
  filename: string
  point_count: number
  area_km2: number
  message: string
}

const ZONES = [
  { zone: 1, name: '長崎県、鹿児島県の一部' },
  { zone: 2, name: '福岡県、佐賀県、熊本県、大分県、宮崎県、鹿児島県' },
  { zone: 3, name: '山口県、島根県、広島県' },
  { zone: 4, name: '香川県、愛媛県、徳島県、高知県' },
  { zone: 5, name: '兵庫県、鳥取県、岡山県' },
  { zone: 6, name: '京都府、大阪府、福井県、滋賀県、三重県、奈良県、和歌山県' },
  { zone: 7, name: '石川県、富山県、岐阜県、愛知県' },
  { zone: 8, name: '新潟県、長野県、山梨県、静岡県' },
  { zone: 9, name: '東京都、福島県、栃木県、茨城県、埼玉県、千葉県、群馬県、神奈川県' },
  { zone: 10, name: '青森県、秋田県、山形県、岩手県、宮城県' },
  { zone: 11, name: '北海道（西部）' },
  { zone: 12, name: '北海道（中央部）' },
  { zone: 13, name: '北海道（東部）' },
  { zone: 14, name: '小笠原諸島' },
  { zone: 15, name: '沖縄県（本島）' },
  { zone: 16, name: '先島諸島' },
  { zone: 17, name: '大東諸島' },
  { zone: 18, name: '沖ノ鳥島' },
  { zone: 19, name: '南鳥島' },
]

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('text')

  // Text conversion state
  const [inputText, setInputText] = useState('')
  const [coordType, setCoordType] = useState<CoordType>('latlon')
  const [inputHeightType, setInputHeightType] = useState<HeightType>('ellipsoid')
  const [outputHeightType, setOutputHeightType] = useState<HeightType>('geoid2024')
  const [zone, setZone] = useState(9)
  const [useIslandCorrection, setUseIslandCorrection] = useState(false)
  const [results, setResults] = useState<ConvertResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // LAS state (currently disabled - 準備中)
  const [lasFile, setLasFile] = useState<File | null>(null)
  const [lasJobs, setLasJobs] = useState<LASJob[]>([])
  const [lasUploading, setLasUploading] = useState(false)
  const [lasError, setLasError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Suppress unused warnings while LAS feature is disabled
  void lasFile; void setLasFile; void lasJobs; void setLasJobs;
  void lasUploading; void setLasUploading; void lasError; void setLasError;
  void fileInputRef; void pollingRef;

  // LASジョブ一覧を取得
  const fetchLasJobs = async () => {
    try {
      const response = await fetch(`${API_URL}/las/jobs`)
      if (response.ok) {
        const data = await response.json()
        setLasJobs(data.jobs)
      }
    } catch {
      // 静かに失敗
    }
  }

  // ポーリング開始
  useEffect(() => {
    if (activeTab === 'las') {
      fetchLasJobs()
      pollingRef.current = setInterval(fetchLasJobs, 3000)
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [activeTab])

  const parseInput = (text: string): PointInput[] => {
    const lines = text.trim().split('\n')
    const points: PointInput[] = []

    for (const line of lines) {
      if (!line.trim()) continue

      // TSV または CSV をパース
      const parts = line.includes('\t') ? line.split('\t') : line.split(',')
      if (parts.length >= 4) {
        points.push({
          name: parts[0].trim(),
          x: parseFloat(parts[1].trim()),
          y: parseFloat(parts[2].trim()),
          z: parseFloat(parts[3].trim()),
        })
      }
    }

    return points
  }

  const handleConvert = async () => {
    setError(null)
    setLoading(true)

    try {
      const points = parseInput(inputText)
      if (points.length === 0) {
        setError('有効なデータがありません。形式: 点名,X,Y,Z')
        setLoading(false)
        return
      }

      const response = await fetch(`${API_URL}/convert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          points,
          input_coord_type: coordType,
          input_height_type: inputHeightType,
          output_height_type: outputHeightType,
          zone: coordType === 'plane' ? zone : null,
          use_island_correction: useIslandCorrection,
        }),
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || '変換に失敗しました')
      }

      const data: ConvertResponse = await response.json()
      setResults(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : '不明なエラー')
    } finally {
      setLoading(false)
    }
  }

  const exportResults = () => {
    if (!results) return

    const headers = ['点名', '緯度', '経度', '入力高', '補正量', '出力高', '離島', '警告']
    const rows = results.points.map(p => [
      p.name,
      p.lat.toFixed(8),
      p.lon.toFixed(8),
      p.input_height.toFixed(4),
      p.geoid_height?.toFixed(4) ?? '',
      p.output_height.toFixed(4),
      p.is_island ? p.island_region : '',
      p.warning ?? '',
    ])

    const tsv = [headers.join('\t'), ...rows.map(r => r.join('\t'))].join('\n')
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'converted_results.tsv'
    a.click()
  }

  // LASファイルアップロード
  const handleLasUpload = async () => {
    if (!lasFile) return

    setLasUploading(true)
    setLasError(null)

    try {
      const formData = new FormData()
      formData.append('file', lasFile)

      const params = new URLSearchParams({
        zone: zone.toString(),
        input_height_type: inputHeightType,
        output_height_type: outputHeightType,
        use_island_correction: useIslandCorrection.toString(),
      })

      const response = await fetch(`${API_URL}/las/upload?${params}`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'アップロードに失敗しました')
      }

      const data: LASUploadResponse = await response.json()
      setLasFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }

      // ジョブ一覧を更新
      fetchLasJobs()
      alert(`${data.message}\nジョブID: ${data.job_id}`)
    } catch (e) {
      setLasError(e instanceof Error ? e.message : '不明なエラー')
    } finally {
      setLasUploading(false)
    }
  }

  // ジョブ削除
  const handleDeleteJob = async (jobId: string) => {
    if (!confirm('このジョブを削除しますか？')) return

    try {
      const response = await fetch(`${API_URL}/las/job/${jobId}`, {
        method: 'DELETE',
      })
      if (response.ok) {
        fetchLasJobs()
      }
    } catch {
      // 静かに失敗
    }
  }

  const formatDate = (isoString: string) => {
    const date = new Date(isoString)
    return date.toLocaleString('ja-JP')
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'pending': return '待機中'
      case 'processing': return '処理中'
      case 'completed': return '完了'
      case 'failed': return 'エラー'
      default: return status
    }
  }

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'pending': return 'status-pending'
      case 'processing': return 'status-processing'
      case 'completed': return 'status-completed'
      case 'failed': return 'status-failed'
      default: return ''
    }
  }

  // Suppress unused warnings while LAS feature is disabled
  void handleLasUpload; void handleDeleteJob; void formatDate;
  void getStatusLabel; void getStatusClass;

  return (
    <div className="container">
      <h1>ジオイド変換ツール</h1>

      <div className="tabs">
        <button
          className={`tab ${activeTab === 'text' ? 'active' : ''}`}
          onClick={() => setActiveTab('text')}
        >
          テキストデータ
        </button>
        <button
          className={`tab ${activeTab === 'las' ? 'active' : ''}`}
          onClick={() => setActiveTab('las')}
        >
          LASファイル
        </button>
      </div>

      <div className="settings">
        {activeTab === 'text' && (
          <div className="setting-group">
            <label>座標形式</label>
            <select value={coordType} onChange={e => setCoordType(e.target.value as CoordType)}>
              <option value="latlon">経緯度（緯度, 経度）</option>
              <option value="plane">平面直角座標（X, Y）</option>
            </select>
          </div>
        )}

        {(activeTab === 'las' || coordType === 'plane') && (
          <div className="setting-group">
            <label>系番号</label>
            <select value={zone} onChange={e => setZone(parseInt(e.target.value))}>
              {ZONES.map(z => (
                <option key={z.zone} value={z.zone}>
                  {z.zone}系: {z.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="setting-group">
          <label>入力高さ</label>
          <select value={inputHeightType} onChange={e => setInputHeightType(e.target.value as HeightType)}>
            <option value="ellipsoid">楕円体高</option>
            <option value="geoid2024">ジオイド2024高（標高）</option>
            <option value="geoid2011">ジオイド2011高（標高）</option>
          </select>
        </div>

        <div className="setting-group">
          <label>出力高さ</label>
          <select value={outputHeightType} onChange={e => setOutputHeightType(e.target.value as HeightType)}>
            <option value="ellipsoid">楕円体高</option>
            <option value="geoid2024">ジオイド2024高（標高）</option>
            <option value="geoid2011">ジオイド2011高（標高）</option>
          </select>
        </div>

        <div className="setting-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={useIslandCorrection}
              onChange={e => setUseIslandCorrection(e.target.checked)}
            />
            離島補正を使用（Hrefconv2024）
          </label>
        </div>
      </div>

      {activeTab === 'text' && (
        <>
          <div className="input-section">
            <label>
              入力データ（TSV/CSV形式: 点名, {coordType === 'latlon' ? '緯度, 経度' : 'X, Y'}, 高さ）
            </label>
            <textarea
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              placeholder={
                coordType === 'latlon'
                  ? 'P1,35.681236,139.767125,50.000\nP2,35.689487,139.691711,45.500'
                  : 'P1,-10000.000,20000.000,50.000\nP2,-10500.000,20500.000,45.500'
              }
              rows={10}
            />
          </div>

          <button onClick={handleConvert} disabled={loading || !inputText.trim()}>
            {loading ? '変換中...' : '変換実行'}
          </button>

          {error && <div className="error">{error}</div>}

          {results && (
            <div className="results">
              <div className="results-header">
                <h2>変換結果</h2>
                <button onClick={exportResults}>TSVエクスポート</button>
              </div>

              {results.has_island_points && !useIslandCorrection && (
                <div className="warning">
                  離島地域の点が含まれています。「離島補正を使用」オプションの使用を検討してください。
                </div>
              )}

              <ResultMap points={results.points} />

              <table>
                <thead>
                  <tr>
                    <th>点名</th>
                    <th>緯度</th>
                    <th>経度</th>
                    <th>入力高</th>
                    <th>補正量</th>
                    <th>出力高</th>
                    <th>警告</th>
                  </tr>
                </thead>
                <tbody>
                  {results.points.map((p, i) => (
                    <tr key={i} className={p.warning ? 'has-warning' : ''}>
                      <td>{p.name}</td>
                      <td>{p.lat.toFixed(8)}</td>
                      <td>{p.lon.toFixed(8)}</td>
                      <td>{p.input_height.toFixed(4)}</td>
                      <td>{p.geoid_height?.toFixed(4) ?? '-'}</td>
                      <td>{p.output_height.toFixed(4)}</td>
                      <td className="warning-cell">{p.warning}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {activeTab === 'las' && (
        <div className="las-section">
          <div className="las-upload">
            <h3>LASファイル変換機能</h3>
            <p className="coming-soon-text">準備中</p>
            <p className="las-note">
              LASファイル（.las, .laz）の高さ変換機能は現在準備中です。<br />
              今しばらくお待ちください。
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
