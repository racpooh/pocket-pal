package dev.finassist.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import dev.finassist.core.BlobStore
import dev.finassist.core.QueueStore
import dev.finassist.core.TokenStore
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Session token at rest: AES-256-GCM with a non-exportable key in the Android Keystore; only the ciphertext is in
 * app-private SharedPreferences (excluded from backup). The token is never logged. If the key becomes unusable
 * (e.g. restored to another device) the token is dropped and the user signs in again.
 */
class KeystoreTokenStore(context: Context) : TokenStore {
    private val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)
    private val alias = "finassist_session_v1"
    @Volatile private var cache: String? = null
    @Volatile private var loaded = false

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(alias, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build())
        return gen.generateKey()
    }

    @Synchronized override fun get(): String? {
        if (loaded) return cache
        loaded = true
        val ct = prefs.getString("ct", null) ?: return null
        val iv = prefs.getString("iv", null) ?: return null
        cache = try {
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
            String(c.doFinal(Base64.decode(ct, Base64.NO_WRAP)), Charsets.UTF_8)
        } catch (e: Exception) {
            prefs.edit().clear().apply(); null
        }
        return cache
    }

    /** Clears only if [expected] is still the stored token (a late 401 of an older session must not log out a newer one). */
    @Synchronized override fun clearIf(expected: String?): Boolean {
        if (expected == null || get() != expected) return false
        set(null); return true
    }

    @Synchronized override fun set(token: String?) {
        cache = token; loaded = true
        if (token == null) { prefs.edit().clear().apply(); return }
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, key())
        prefs.edit()
            .putString("iv", Base64.encodeToString(c.iv, Base64.NO_WRAP))
            .putString("ct", Base64.encodeToString(c.doFinal(token.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP))
            .apply()
    }
}

/** Upload-queue state (no image bytes, no extracted content): sha256, state, server upload id. */
class PrefsQueueStore(context: Context) : QueueStore {
    private val prefs = context.getSharedPreferences("upload_queue", Context.MODE_PRIVATE)
    override fun load(): String? = prefs.getString("state", null)
    override fun save(json: String) { prefs.edit().putString("state", json).commit() } // commit: persisted before the network call
}

/** Copies of picked images until the server confirms receipt. App-private, not backed up; deleted after upload. */
class FileBlobStore(context: Context) : BlobStore {
    private val dir = File(context.noBackupFilesDir, "upload_queue").apply { mkdirs() }
    private fun f(key: String): File {
        require(key.matches(Regex("[0-9a-f]{64}"))) { "bad key" }
        return File(dir, key)
    }
    override fun put(key: String, bytes: ByteArray) { f(key).writeBytes(bytes) }
    override fun get(key: String): ByteArray? = f(key).takeIf { it.exists() }?.readBytes()
    override fun delete(key: String) { f(key).delete() }
    fun deleteAll() { dir.listFiles()?.forEach { it.delete() } }
}
