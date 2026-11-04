<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowDownWideNarrow, ArrowLeft, Check, ChevronRight, Folder, FolderOpen, Image as ImageIcon, Images, LoaderCircle, QrCode, RefreshCw, Search, Settings2, X } from '@lucide/vue'
import PhotoSwipe from 'photoswipe'
import QRCode from 'qrcode'

interface FolderEntry { name: string; path: string }
interface ImageEntry extends FolderEntry {
  width: number; height: number; size: number; modified: number; version: string
  src: string; thumbnail: string
}
interface Listing { path: string; name: string; folders: FolderEntry[]; images: ImageEntry[]; skipped: string[] }
interface Settings { folder: string; can_configure: boolean; urls: string[]; formats: string[] }

const settings = ref<Settings | null>(null)
const listing = ref<Listing | null>(null)
const currentPath = ref(new URLSearchParams(location.search).get('path') || '')
const loading = ref(false)
const error = ref('')
const query = ref('')
const sort = ref('name')
const compact = ref(false)
const showSettings = ref(false)
const showConnect = ref(false)
const folderInput = ref('')
const saving = ref(false)
const settingsError = ref('')
const qrImage = ref('')
const connectUrl = ref('')
const copied = ref(false)
const failedImages = ref(new Set<string>())
const grid = ref<HTMLElement | null>(null)
let controller: AbortController | undefined
let viewer: PhotoSwipe | undefined
let modalTrigger: HTMLElement | null = null

// ダイアログを開くと入力先へフォーカスし、閉じると元の操作位置とスクロールを戻す。
watch(() => showSettings.value || showConnect.value, async (open) => {
  if (open) {
    modalTrigger = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'
    await nextTick()
    document.querySelector<HTMLElement>('.modal input:not([readonly]), .modal select')?.focus()
    if (!document.querySelector('.modal input:not([readonly]), .modal select')) {
      document.querySelector<HTMLElement>('.modal-close')?.focus()
    }
  } else {
    document.body.style.overflow = ''
    modalTrigger?.focus({ preventScroll: true })
  }
})

// フィルターと並び順を画像に適用し、一覧とスワイプ順を一致させる。
const visibleImages = computed(() => {
  const images = [...(listing.value?.images || [])].filter(image => image.name.toLocaleLowerCase().includes(query.value.toLocaleLowerCase()))
  if (sort.value === 'newest') images.sort((a, b) => b.modified - a.modified)
  if (sort.value === 'oldest') images.sort((a, b) => a.modified - b.modified)
  if (sort.value === 'reverse') images.reverse()
  return images
})
const visibleFolders = computed(() => (listing.value?.folders || []).filter(folder => folder.name.toLocaleLowerCase().includes(query.value.toLocaleLowerCase())))
const breadcrumbs = computed(() => {
  const parts = currentPath.value.split('/').filter(Boolean)
  return parts.map((name, index) => ({ name, path: parts.slice(0, index + 1).join('/') }))
})
const rootName = computed(() => settings.value?.folder.split(/[\\/]/).filter(Boolean).at(-1) || 'ライブラリ')

// APIの失敗を画面に出せるメッセージへ変換し、成功時のJSONを返す。
async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const message = typeof body.detail === 'string' ? body.detail : `読み込みに失敗しました（${response.status}）`
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

// フォルダを読み込み、古い通信を中止してURL・サムネイル・表示状態を更新する。
async function loadFolder(path: string, historyMode: 'push' | 'replace' | 'none' = 'push') {
  controller?.abort()
  const active = new AbortController()
  controller = active
  loading.value = true
  error.value = ''
  try {
    const data = await request<Listing>(`/api/browse?${new URLSearchParams({ path })}`, { signal: active.signal })
    data.images = data.images.map(image => {
      const params = new URLSearchParams({ path: image.path, v: image.version })
      return { ...image, src: `/api/image?${params}`, thumbnail: `/api/thumbnail?${params}` }
    })
    listing.value = data
    currentPath.value = data.path
    query.value = ''
    failedImages.value = new Set()
    const url = data.path ? `/?${new URLSearchParams({ path: data.path })}` : '/'
    if (historyMode === 'push') history.pushState({}, '', url)
    if (historyMode === 'replace') history.replaceState({}, '', url)
    window.scrollTo({ top: 0, behavior: 'instant' })
  } catch (reason) {
    if (!active.signal.aborted) error.value = reason instanceof Error ? reason.message : 'フォルダを読み込めません。'
  } finally {
    if (controller === active) loading.value = false
  }
}

// 初期設定を取得し、設定済みなら指定されたフォルダを開く。
async function initialize() {
  loading.value = true
  error.value = ''
  try {
    settings.value = await request<Settings>('/api/settings')
    folderInput.value = settings.value.folder
    connectUrl.value = settings.value.urls[0] || ''
    if (settings.value.folder) await loadFolder(currentPath.value, 'replace')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'サーバーに接続できません。'
  } finally {
    loading.value = false
  }
}

// PCで入力した閲覧フォルダを保存し、新しいルートの一覧に切り替える。
async function saveFolder() {
  saving.value = true
  settingsError.value = ''
  try {
    await request('/api/settings', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: folderInput.value }),
    })
    settings.value = await request<Settings>('/api/settings')
    folderInput.value = settings.value.folder
    showSettings.value = false
    await loadFolder('', 'push')
  } catch (reason) {
    settingsError.value = reason instanceof Error ? reason.message : '設定を保存できません。'
  } finally {
    saving.value = false
  }
}

// 表示中の画像群でPhotoSwipeを開き、画像名とタップ元の位置を引き継ぐ。
function openGallery(index: number) {
  viewer?.destroy()
  const images = [...visibleImages.value]
  viewer = new PhotoSwipe({
    dataSource: images.map(image => ({ src: image.src, msrc: image.thumbnail, width: image.width, height: image.height, alt: image.name })),
    index, loop: false, bgOpacity: 0.96,
    showHideAnimationType: 'fade',
    closeTitle: '閉じる', zoomTitle: '拡大・縮小', arrowPrevTitle: '前の画像', arrowNextTitle: '次の画像',
    errorMsg: '画像を読み込めません。ファイルを確認して一覧を更新してください。',
    padding: { top: 52, bottom: 64, left: 12, right: 12 },
  })
  viewer.on('uiRegister', () => {
    viewer!.ui!.registerElement({
      name: 'image-caption', order: 9, isButton: false, appendTo: 'root',
      onInit(element, pswp) {
        // スワイプで画像が切り替わるたびに、文字列としてファイル名を表示する。
        function updateCaption() {
          const image = images[pswp.currIndex]
          element.textContent = image ? image.name : ''
          element.setAttribute('aria-live', 'polite')
        }
        updateCaption()
        pswp.on('change', updateCaption)
      },
    })
  })
  const target = grid.value?.querySelectorAll<HTMLButtonElement>('.image-card')[index]
  viewer.on('destroy', () => target?.focus({ preventScroll: true }))
  viewer.init()
}

// 接続先選択に合わせてQRコードをローカル生成し、生成失敗を画面に表示する。
async function generateQr() {
  qrImage.value = ''
  copied.value = false
  if (!connectUrl.value) return
  try {
    qrImage.value = await QRCode.toDataURL(connectUrl.value, { width: 260, margin: 2, color: { dark: '#101315', light: '#ffffff' } })
  } catch {
    error.value = 'QRコードを作成できません。表示されたURLを直接開いてください。'
  }
}

// 接続ダイアログを開き、URL選択欄にフォーカスしてQRコードを表示する。
async function openConnect() {
  showConnect.value = true
  await generateQr()
  await nextTick()
  document.querySelector<HTMLSelectElement>('#connection-url')?.focus()
}

// 接続URLをコピーし、クリップボードが使えない環境ではURL文字列を選択する。
async function copyUrl() {
  try {
    await navigator.clipboard.writeText(connectUrl.value)
    copied.value = true
  } catch {
    const input = document.querySelector<HTMLInputElement>('#copy-url')
    input?.focus()
    input?.select()
  }
}

// ブラウザの戻る・進む操作で、URLに対応するフォルダを再表示する。
function onPopState() {
  viewer?.close()
  const path = new URLSearchParams(location.search).get('path') || ''
  void loadFolder(path, 'none')
}

// Escapeでダイアログを閉じ、モーダル表示中のTab移動を内部に保つ。
function onKeyDown(event: KeyboardEvent) {
  if (!showConnect.value && !showSettings.value) return
  if (event.key === 'Escape') {
    showConnect.value = false
    showSettings.value = false
  }
  if (event.key === 'Tab') {
    const elements = [...(document.querySelector('.modal')?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, a[href]') || [])]
    const first = elements[0]
    const last = elements.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
}

onMounted(() => {
  void initialize()
  window.addEventListener('popstate', onPopState)
  window.addEventListener('keydown', onKeyDown)
})
onUnmounted(() => {
  controller?.abort()
  viewer?.destroy()
  window.removeEventListener('popstate', onPopState)
  window.removeEventListener('keydown', onKeyDown)
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="app-shell">
    <header class="header">
      <a class="brand" href="/" @click.prevent="settings?.folder && loadFolder('')">
        <span class="brand-mark"><Images :size="23" :stroke-width="1.6" /></span>
        <span>Local Gallery<span class="brand-sub">YOUR FILES, YOUR SPACE</span></span>
      </a>
      <div class="header-actions">
        <span class="local-badge"><span></span> ローカル接続</span>
        <button class="icon-button" title="フォルダ設定" aria-label="フォルダ設定" @click="showSettings = true; settingsError = ''"><Settings2 :size="20" /></button>
        <button class="connect-button" @click="openConnect"><QrCode :size="18" /><span>スマホで開く</span></button>
      </div>
    </header>

    <main>
      <template v-if="settings && !settings.folder">
        <section class="welcome">
          <span class="welcome-icon"><FolderOpen :size="38" :stroke-width="1.3" /></span>
          <p class="eyebrow">YOUR OWN LITTLE GALLERY</p>
          <h1>PCの画像を、手元のブラウザで。</h1>
          <p class="welcome-description">フォルダを開いて、一覧から気になる一枚へ。<br />スマホではスワイプで、次の画像へ。</p>
          <form v-if="settings.can_configure" class="setup-form" @submit.prevent="saveFolder">
            <label for="initial-folder">閲覧するPCのフォルダ</label>
            <input id="initial-folder" v-model="folderInput" placeholder="例：C:\Users\yourname\Pictures" required autocomplete="off" />
            <p class="field-note">エクスプローラーのアドレスバーから、フォルダのパスをコピーしてください。</p>
            <p v-if="settingsError" class="error-text" role="alert">{{ settingsError }}</p>
            <button class="primary-button" :disabled="saving"><LoaderCircle v-if="saving" class="spin" :size="18" /><FolderOpen v-else :size="18" />{{ saving ? '開いています…' : 'このフォルダを開く' }}</button>
          </form>
          <p v-else class="notice">PCの <strong>http://localhost:8000</strong> で、閲覧するフォルダを設定してください。設定後にこのページを再読み込みしてください。</p>
          <p class="privacy-note">画像はPC内に保存されたまま。同じWi-Fiから閲覧できます。</p>
        </section>
      </template>

      <template v-else-if="settings?.folder">
        <nav class="breadcrumbs" aria-label="現在のフォルダ">
          <button @click="loadFolder('')"><FolderOpen :size="16" />{{ rootName }}</button>
          <template v-for="crumb in breadcrumbs" :key="crumb.path"><ChevronRight :size="14" /><button @click="loadFolder(crumb.path)">{{ crumb.name }}</button></template>
        </nav>
        <section class="collection-heading">
          <div><p class="eyebrow">YOUR COLLECTION</p><h1>{{ listing?.name || rootName }}</h1><p class="collection-count">{{ listing?.images.length || 0 }} 枚の画像<span v-if="listing?.folders.length"> · {{ listing.folders.length }} フォルダ</span></p></div>
          <button class="icon-button refresh" title="一覧を更新" aria-label="一覧を更新" :disabled="loading" @click="loadFolder(currentPath, 'none')"><RefreshCw :size="19" :class="{ spin: loading }" /></button>
        </section>
        <div class="toolbar">
          <label class="search"><Search :size="18" /><input v-model="query" placeholder="このフォルダを検索" aria-label="ファイル名で絞り込み" /><button v-if="query" class="clear-button" aria-label="検索をクリア" @click="query = ''"><X :size="15" /></button></label>
          <div class="toolbar-options"><label class="sort"><ArrowDownWideNarrow :size="17" /><select v-model="sort" aria-label="画像の並び順"><option value="name">名前順</option><option value="reverse">名前の逆順</option><option value="newest">更新が新しい順</option><option value="oldest">更新が古い順</option></select></label><button class="density-button" :aria-pressed="compact" @click="compact = !compact">{{ compact ? '大きく表示' : '小さく表示' }}</button></div>
        </div>
        <div v-if="error" class="notice error-notice" role="alert"><span>{{ error }}</span><button @click="loadFolder(currentPath, 'none')">再読み込み</button><button v-if="currentPath" @click="loadFolder('')">ルートに戻る</button></div>
        <div v-if="listing?.skipped.length" class="notice">{{ listing.skipped.length }} 件の画像を読み込めませんでした：{{ listing.skipped.join('、') }}</div>
        <section v-if="visibleFolders.length || currentPath" class="folder-grid" aria-label="フォルダ">
          <button v-if="currentPath" class="folder-card parent-folder" @click="loadFolder(currentPath.split('/').slice(0, -1).join('/'))"><ArrowLeft :size="21" /><span>上のフォルダ</span></button>
          <button v-for="folder in visibleFolders" :key="folder.path" class="folder-card" @click="loadFolder(folder.path)"><Folder :size="24" :stroke-width="1.5" /><span>{{ folder.name }}</span><ChevronRight :size="16" /></button>
        </section>
        <div v-if="loading" class="loading-line" role="status"><LoaderCircle class="spin" :size="17" />フォルダを読み込んでいます…</div>
        <section ref="grid" class="image-grid" :class="{ compact, 'is-loading': loading }" aria-label="画像一覧" :aria-busy="loading" :inert="loading">
          <button v-for="(image, index) in visibleImages" :key="image.path + image.version" class="image-card" :title="image.name" @click="openGallery(index)">
            <div class="image-frame"><img v-if="!failedImages.has(image.path)" :src="image.thumbnail" :alt="image.name" loading="lazy" decoding="async" @error="failedImages.add(image.path)" /><div v-else class="thumbnail-error"><ImageIcon :size="26" /><span>読み込めません</span></div><span class="image-number">{{ String(index + 1).padStart(2, '0') }}</span><span class="image-dimensions">{{ image.width }} × {{ image.height }}</span></div>
            <span class="image-name">{{ image.name }}</span>
          </button>
        </section>
        <div v-if="listing && !visibleImages.length && !visibleFolders.length && !loading && !error" class="empty-state"><Images :size="36" :stroke-width="1.2" /><h2>{{ query ? '一致するファイルがありません' : 'このフォルダには画像がありません' }}</h2><p>{{ query ? '別の名前で検索してみてください。' : '別のフォルダを開くか、画像を追加して一覧を更新してください。' }}</p></div>
        <footer v-if="visibleImages.length" class="gallery-footer"><span>{{ visibleImages.length }} IMAGES</span><span>タップで拡大 · スワイプで次の画像へ</span></footer>
      </template>
      <div v-if="error && !settings?.folder" class="notice error-notice" role="alert"><span>{{ error }}</span><button @click="initialize">再接続</button></div>
      <div v-if="loading && !settings" class="empty-state" role="status"><LoaderCircle class="spin" :size="28" /><p>ライブラリに接続しています…</p></div>
    </main>

    <div v-if="showSettings" class="modal-backdrop" @click.self="showSettings = false">
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <button class="modal-close icon-button" aria-label="閉じる" @click="showSettings = false"><X :size="21" /></button>
        <span class="modal-symbol"><FolderOpen :size="25" /></span><h2 id="settings-title">フォルダ設定</h2><p>このフォルダと、その中のサブフォルダを閲覧できます。</p>
        <form v-if="settings?.can_configure" class="setup-form" @submit.prevent="saveFolder"><label for="settings-folder">閲覧フォルダの絶対パス</label><input id="settings-folder" v-model="folderInput" required autocomplete="off" /><p v-if="settingsError" class="error-text" role="alert">{{ settingsError }}</p><button class="primary-button" :disabled="saving"><LoaderCircle v-if="saving" class="spin" :size="18" />{{ saving ? '保存しています…' : '保存して開く' }}</button></form>
        <div v-else class="notice">フォルダの変更はPCの localhost 画面で行ってください。<p class="folder-path">{{ settings?.folder }}</p></div>
        <p class="field-note">対応形式：{{ settings?.formats.join(' / ') }}</p>
      </section>
    </div>
    <div v-if="showConnect" class="modal-backdrop" @click.self="showConnect = false">
      <section class="modal connect-modal" role="dialog" aria-modal="true" aria-labelledby="connect-title">
        <button class="modal-close icon-button" aria-label="閉じる" @click="showConnect = false"><X :size="21" /></button>
        <span class="modal-symbol"><QrCode :size="25" /></span><h2 id="connect-title">スマホで、続きを。</h2><p>PCと同じWi-Fiに接続して、<br />スマホのカメラでQRコードを読み取ってください。</p>
        <template v-if="settings?.urls.length"><img v-if="qrImage" class="qr-code" :src="qrImage" alt="スマホ接続用QRコード" /><label class="url-select" for="connection-url">接続先<select id="connection-url" v-model="connectUrl" @change="generateQr"><option v-for="url in settings.urls" :key="url" :value="url">{{ url }}</option></select></label><div class="copy-row"><input id="copy-url" :value="connectUrl" readonly aria-label="接続URL" /><button class="icon-button" :aria-label="copied ? 'コピーしました' : 'URLをコピー'" @click="copyUrl"><Check v-if="copied" :size="18" /><span v-else>コピー</span></button></div></template>
        <p v-else class="notice">接続先が見つかりません。PCのWi-Fi接続を確認して、ページを再読み込みしてください。</p>
        <p class="field-note">接続できない場合は、別の接続先を選択してください。Windowsのファイアウォールで、このアプリのプライベートネットワーク通信を許可する必要があります。</p>
      </section>
    </div>
  </div>
</template>
