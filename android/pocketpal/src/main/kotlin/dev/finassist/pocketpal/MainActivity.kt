package dev.finassist.pocketpal

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.*
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import androidx.work.*
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var store: ScanStore
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private val origin = BuildConfig.WEB_ORIGIN
    private val epoch = java.util.concurrent.atomic.AtomicInteger(0)
    private fun trusted(url: String?): Boolean {
        val a = Uri.parse(url ?: ""); val b = Uri.parse(origin)
        return a.scheme == b.scheme && a.host == b.host && a.port == b.port
    }
    private fun status(): JSONObject {
        val same = store.ownsSession()
        val result = if (same) store.status(GalleryWorker.permission(this)) else JSONObject()
            .put("available", true).put("enabled", false).put("permission", GalleryWorker.permission(this))
            .put("windowDays", 30).put("dailyLimit", ScanPolicy.DAILY_CAP).put("attemptsToday", 0)
            .put("lastScan", 0).put("message", "Scanning is off for this session. Enable it after signing in.")
        return result.put("busy", same && GalleryWorker.busy.get()).put("owner_bound", same)
            .put("daily_remaining", if (same) (ScanPolicy.DAILY_CAP - store.attempts()).coerceAtLeast(0) else ScanPolicy.DAILY_CAP)
    }
    private fun publish() { if (trusted(web.url)) web.evaluateJavascript("window.__pocketPalStatus=${status()};window.dispatchEvent(new CustomEvent('pocketpal-native-status',{detail:window.__pocketPalStatus}));", null) }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        check(origin.startsWith("https://") || (BuildConfig.DEBUG && origin == "http://127.0.0.1:3002"))
        store = ScanStore(this)
        web = WebView(this)
        web.settings.apply { javaScriptEnabled = true; domStorageEnabled = true; allowFileAccess = false; allowContentAccess = false; mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW; setSupportMultipleWindows(false) }
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false)
        WebView.setWebContentsDebuggingEnabled(false)
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = !trusted(request.url.toString())
            override fun onPageFinished(view: WebView, url: String) {
                if (!trusted(url)) return
                web.evaluateJavascript("""window.PocketPalNative={getStatus:()=>{PocketPalChannel.postMessage('{"action":"status"}');return JSON.stringify(window.__pocketPalStatus||{})},configure:(enabled)=>PocketPalChannel.postMessage(JSON.stringify({action:'configure',enabled:!!enabled})),scanNow:()=>PocketPalChannel.postMessage('{"action":"scanNow"}'),pause:()=>PocketPalChannel.postMessage('{"action":"pause"}'),requestPermission:()=>PocketPalChannel.postMessage('{"action":"requestPermission"}')};""", null)
                publish()
            }
            override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: android.net.http.SslError) { handler.cancel() }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
                fileCallback?.onReceiveValue(null); fileCallback = callback
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type = "image/*"; putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("image/jpeg", "image/png")); putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true); addCategory(Intent.CATEGORY_OPENABLE) }
                startActivityForResult(intent, 42); return true
            }
        }
        if (WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            WebViewCompat.addWebMessageListener(web, "PocketPalChannel", setOf(origin)) { _, message, sourceOrigin, isMainFrame, _ ->
                if (isMainFrame && trusted(sourceOrigin.toString()) && trusted(web.url)) {
                    runCatching { JSONObject(message.data ?: "{}").let { handle(it) } }
                }
            }
        }
        setContentView(web); web.loadUrl(if (CookieManager.getInstance().getCookie(origin).isNullOrBlank()) "$origin/connect" else origin)
    }
    private fun handle(message: JSONObject) {
        when (message.optString("action")) {
            "status" -> publish()
            "pause" -> stop()
            "requestPermission" -> permission()
            "configure" -> if (!message.optBoolean("enabled")) stop() else AlertDialog.Builder(this)
                .setTitle("Enable 30-day slip scanning?")
                .setMessage("Only likely slips with a capture date in the last 30 days are uploaded to your server and Anthropic for processing. The local English-text filter can miss Thai-only slips and can select a non-slip. Maximum 20 upload attempts per day. Your photo permission and server consent must also be enabled. Background scanning may be delayed; you can pause anytime.")
                .setNegativeButton("Cancel", null).setPositiveButton("Enable") { _, _ -> enable() }.show()
            "scanNow" -> if (store.enabled) enqueue() else { store.note("Enable scanning first."); publish() }
        }
    }
    private fun enable() {
        val attempt = epoch.incrementAndGet()
        Thread {
            try {
                val api = NativeApi(); val id = api.get("/api/session").getString("user_id")
                check(api.allowed(id))
                runOnUiThread {
                    if (isFinishing || isDestroyed || epoch.get() != attempt || !api.unchanged()) return@runOnUiThread
                    store.bind(id, api.cookie); store.enabled = true
                    val work = PeriodicWorkRequestBuilder<GalleryWorker>(15, TimeUnit.MINUTES).setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build()
                    WorkManager.getInstance(this).enqueueUniquePeriodicWork("gallery-periodic", ExistingPeriodicWorkPolicy.UPDATE, work)
                    if (GalleryWorker.permission(this) == "denied") permission() else enqueue()
                    publish()
                }
            } catch (_: Exception) {
                runOnUiThread {
                    if (!isDestroyed && epoch.get() == attempt) {
                        store.enabled = false; store.note("Sign in and enable photo-processing consent before scanning."); publish()
                    }
                }
            }
        }.start()
    }
    private fun stop() { epoch.incrementAndGet(); store.enabled = false; WorkManager.getInstance(this).cancelUniqueWork("gallery-periodic"); WorkManager.getInstance(this).cancelUniqueWork("gallery-now"); store.note("Scanning paused. An upload already in flight may finish."); publish() }
    private fun enqueue() {
        val work = OneTimeWorkRequestBuilder<GalleryWorker>().setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build()
        WorkManager.getInstance(this).enqueueUniqueWork("gallery-now", ExistingWorkPolicy.KEEP, work)
        // Status is polled by the web settings view and refreshed on resume.
        publish()
    }
    private fun permission() {
        val p = if (Build.VERSION.SDK_INT >= 34) arrayOf(Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
            else if (Build.VERSION.SDK_INT >= 33) arrayOf(Manifest.permission.READ_MEDIA_IMAGES) else arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
        requestPermissions(p, 41)
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) { super.onRequestPermissionsResult(requestCode, permissions, grantResults); publish(); if (store.enabled && GalleryWorker.permission(this) != "denied") enqueue() }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) { super.onActivityResult(requestCode, resultCode, data); if (requestCode == 42) { val uris = if (resultCode != RESULT_OK) null else data?.clipData?.let { clip -> Array(clip.itemCount) { clip.getItemAt(it).uri } } ?: data?.data?.let { arrayOf(it) }; fileCallback?.onReceiveValue(uris); fileCallback = null } }
    override fun onResume() { super.onResume(); if (::web.isInitialized) publish() }
    override fun onDestroy() { epoch.incrementAndGet(); fileCallback?.onReceiveValue(null); web.destroy(); super.onDestroy() }
}
