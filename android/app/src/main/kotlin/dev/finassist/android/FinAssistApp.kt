package dev.finassist.android

import android.app.Application
import dev.finassist.core.ApiClient
import dev.finassist.core.ApiUploadAdapter
import dev.finassist.core.UploadQueue
import dev.finassist.core.UrlConnectionTransport

class FinAssistApp : Application() {
    lateinit var api: ApiClient
        private set
    lateinit var queue: UploadQueue
        private set
    lateinit var blobs: FileBlobStore
        private set
    lateinit var queueStore: PrefsQueueStore
        private set

    override fun onCreate() {
        super.onCreate()
        // BaseUrlPolicy (in ApiClient) refuses http:// in release builds and any non-local http:// in debug builds.
        api = ApiClient(BuildConfig.API_BASE_URL, UrlConnectionTransport(), KeystoreTokenStore(this), debugBuild = BuildConfig.DEBUG)
        blobs = FileBlobStore(this)
        queueStore = PrefsQueueStore(this)
        queue = UploadQueue(queueStore, blobs, ApiUploadAdapter(api))
    }

    /** Logout discards unsent local copies and the queue, so the next account on this phone starts clean. */
    fun resetQueue() {
        queueStore.save("""{"blocked":null,"entries":[]}""")
        blobs.deleteAll()
        queue = UploadQueue(queueStore, blobs, ApiUploadAdapter(api))
    }
}
