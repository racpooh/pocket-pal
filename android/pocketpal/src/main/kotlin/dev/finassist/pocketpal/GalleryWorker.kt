package dev.finassist.pocketpal

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.MediaStore
import android.content.ContentUris
import androidx.work.Worker
import androidx.work.WorkerParameters
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class GalleryWorker(context: Context, params: WorkerParameters) : Worker(context, params) {
    companion object {
        val busy = AtomicBoolean(false)
        fun permission(context: Context): String {
            fun granted(p: String) = context.checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED
            return when {
                Build.VERSION.SDK_INT >= 33 && granted(Manifest.permission.READ_MEDIA_IMAGES) -> "full"
                Build.VERSION.SDK_INT >= 34 && granted(Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED) -> "selected"
                Build.VERSION.SDK_INT <= 32 && granted(Manifest.permission.READ_EXTERNAL_STORAGE) -> "full"
                else -> "denied"
            }
        }
    }
    override fun doWork(): Result {
        if (!busy.compareAndSet(false, true)) return Result.success()
        val store = ScanStore(applicationContext)
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        var scanned = 0; var candidates = 0; var uploaded = 0; var attempted = 0
        // Census (metadata only: id + capture date) explains why photos are or are not in the 30-day window.
        val counts = linkedMapOf(
            "visibleTotal" to 0, "undated" to 0, "olderThanWindow" to 0, "futureDated" to 0, "inWindow" to 0,
            "alreadyUploaded" to 0, "alreadyFiltered" to 0, "serverRefusedBefore" to 0, "legacyRechecked" to 0,
            "alreadyChecked" to 0, "unsupported" to 0, "outsideConsent" to 0, "unreadable" to 0, "checked" to 0,
            "filteredOut" to 0, "filteredMoneyOnly" to 0, "candidates" to 0, "accepted" to 0)
        val labels = linkedMapOf("filterVersion" to ScanPolicy.FILTER_VERSION.toString(), "permissionMode" to "unknown")
        var stage = "starting"
        fun report(value: String) { stage = value; store.progress(value, counts, labels) }
        fun increment(key: String) { counts[key] = counts.getValue(key) + 1 }
        val flt = "flt:v${ScanPolicy.FILTER_VERSION}:"
        try {
            report("checking_access")
            if (!store.enabled || store.owner.isBlank()) return Result.success()
            val mode = permission(applicationContext)
            labels["permissionMode"] = mode
            if (mode == "denied") { report("permission_denied"); store.note("Photo permission is unavailable. Select photos or grant access in Settings."); return Result.success() }
            val owner = store.owner
            val api = NativeApi()
            if (!api.allowed(owner)) { store.enabled = false; report("session_or_consent_required"); store.note("Scanning paused: sign in again and check photo consent."); return Result.success() }
            val now = System.currentTimeMillis()
            report("counting_photos")
            applicationContext.contentResolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                arrayOf(MediaStore.Images.Media._ID, MediaStore.Images.Media.DATE_TAKEN), null, null, null)?.use { c ->
                counts["visibleTotal"] = c.count
                while (c.moveToNext()) {
                    val taken = if (c.isNull(1)) null else c.getLong(1)
                    when (ScanPolicy.dateClass(taken, now)) {
                        ScanPolicy.DateClass.UNDATED -> increment("undated")
                        ScanPolicy.DateClass.OLDER -> increment("olderThanWindow")
                        ScanPolicy.DateClass.FUTURE -> increment("futureDated")
                        ScanPolicy.DateClass.IN_WINDOW -> Unit
                    }
                }
            }
            val projection = arrayOf(MediaStore.Images.Media._ID, MediaStore.Images.Media.DATE_TAKEN, MediaStore.Images.Media.MIME_TYPE, MediaStore.Images.Media.SIZE)
            // Unknown capture dates are deliberately excluded; date-added is NOT capture time.
            val selection = "${MediaStore.Images.Media.DATE_TAKEN} >= ? AND ${MediaStore.Images.Media.DATE_TAKEN} <= ?"
            report("finding_photos")
            applicationContext.contentResolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, projection, selection,
                arrayOf((now - ScanPolicy.WINDOW_MS).toString(), now.toString()), "${MediaStore.Images.Media.DATE_TAKEN} DESC")?.use { cursor ->
                counts["inWindow"] = cursor.count
                report("checking_photos")
                while (cursor.moveToNext()) {
                    if (isStopped || !store.enabled || store.owner != owner || !api.unchanged() || permission(applicationContext) == "denied") break
                    if (!ScanPolicy.mayAttempt(scanned, attempted, store.attempts())) { report("limit_reached"); break }
                    val id = cursor.getLong(0); val captured = cursor.getLong(1); val mime = cursor.getString(2) ?: continue
                    val size = cursor.getLong(3)
                    if (!ScanPolicy.recent(captured, now) || mime !in listOf("image/jpeg", "image/png") || size <= 0 || size > ScanPolicy.MAX_BYTES) { increment("unsupported"); continue }
                    val metadataKey = "$owner:$id:$captured:$size"
                    // Never send twice: an accepted photo is skipped by metadata here and by content hash below.
                    if (store.seen("acc:$metadataKey")) { increment("alreadyUploaded"); increment("alreadyChecked"); continue }
                    if (store.seen("rej:$metadataKey")) { increment("serverRefusedBefore"); increment("alreadyChecked"); continue }
                    if (store.seen("$flt$metadataKey")) { increment("alreadyFiltered"); increment("alreadyChecked"); continue }
                    val legacy = store.seen(metadataKey) // marked by filter v1 (accepted, filtered or refused; cause not stored)
                    if (!api.consentDateAllowed(captured)) { increment("outsideConsent"); continue }
                    val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
                    val bytes = applicationContext.contentResolver.openInputStream(uri)?.use { ScanPolicy.readBounded(it) }
                    if (bytes == null) { increment("unreadable"); continue }
                    if (bytes.size > ScanPolicy.MAX_BYTES) { increment("unsupported"); continue }
                    scanned++
                    increment("checked")
                    if (legacy) increment("legacyRechecked")
                    report("local_ocr")
                    val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
                    if (store.seen("$owner:$digest")) { store.mark("acc:$metadataKey"); increment("alreadyUploaded"); continue }
                    val bounds = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
                    android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
                    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) { increment("unreadable"); continue }
                    val options = android.graphics.BitmapFactory.Options().apply {
                        var sample = 1; while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 2048) sample *= 2
                        inSampleSize = sample
                    }
                    val bitmap = android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
                    if (bitmap == null) { increment("unreadable"); continue }
                    val text = try { Tasks.await(recognizer.process(InputImage.fromBitmap(bitmap, 0)), 30, TimeUnit.SECONDS).text } finally { bitmap.recycle() }
                    if (!ScanPolicy.candidate(text)) {
                        increment("filteredOut"); if (ScanPolicy.moneyOnly(text)) increment("filteredMoneyOnly")
                        store.mark("$flt$metadataKey"); report("checking_photos"); continue
                    }
                    candidates++
                    increment("candidates")
                    if (isStopped || !store.enabled || store.owner != owner || permission(applicationContext) == "denied" || !api.allowed(owner)) break
                    attempted++
                    store.reserveAttempt() // reserve BEFORE network; uncertain responses also consume the daily bound
                    report("uploading")
                    val code = api.upload(bytes, mime, captured, owner)
                    counts["lastHttpStatus"] = code
                    when {
                        code in 200..299 -> { store.mark("acc:$metadataKey"); store.mark("$owner:$digest"); uploaded++; increment("accepted") }
                        code == 401 || code == 403 || code == 409 -> { store.enabled = false; report("upload_rejected"); break }
                        code == 422 -> store.mark("rej:$metadataKey") // outside consent window / needs manual confirmation
                        else -> { report("upload_failed"); break } // retain for a future bounded retry; do not spin through the album
                    }
                }
            }
            if (stage !in listOf("limit_reached", "upload_rejected", "upload_failed")) report(if (isStopped || !store.enabled) "paused" else "finished")
            else store.progress(stage, counts, labels)
            val undated = counts.getValue("undated")
            store.note("Checked $scanned photos locally; $candidates likely slips; $uploaded uploaded." +
                (if (undated > 0) " $undated photos have no capture date and are never sent automatically; upload them in Chat." else "") +
                (if (mode == "selected") " Only the photos you selected are visible to Pocket Pal." else ""))
            return Result.success()
        } catch (_: Exception) {
            report("error_during_$stage")
            // No exception text, file names, OCR text, image bytes or server bodies are logged.
            store.note("Scan paused by a permission, network or processing error. Check access and use Scan now to retry.")
            return Result.success()
        } finally { recognizer.close(); busy.set(false) }
    }
}
