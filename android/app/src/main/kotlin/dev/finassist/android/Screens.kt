package dev.finassist.android

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import dev.finassist.core.ActivityModel
import dev.finassist.core.BlockReason
import dev.finassist.core.LocalState
import dev.finassist.core.Money
import dev.finassist.core.MoneyText
import dev.finassist.core.QueueEntry
import dev.finassist.core.ResolveOutcome
import dev.finassist.core.ReviewView
import dev.finassist.core.UploadLabels
import dev.finassist.core.UploadLimits
import dev.finassist.core.list
import dev.finassist.core.long
import dev.finassist.core.obj
import dev.finassist.core.objs
import dev.finassist.core.str
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/*
 * Vertical slice 1 (docs/design/13 §4): sign in → consent → upload → review → activity, in the pocket-pal style
 * (Theme.kt). Every value on screen comes from the backend or from the user; there is no sample or demo data.
 */

private val BKK: ZoneId = ZoneId.of("Asia/Bangkok")
private val SCREEN = Modifier.padding(horizontal = 18.dp)

@Composable
private fun Field(label: String, value: String, onChange: (String) -> Unit, number: Boolean = false, password: Boolean = false,
                  modifier: Modifier = Modifier) {
    OutlinedTextField(value, onChange, label = { Text(label) }, singleLine = true, modifier = modifier.fillMaxWidth(), shape = Pal.CtlShape,
        keyboardOptions = KeyboardOptions(keyboardType = when { password -> KeyboardType.Password; number -> KeyboardType.Decimal; else -> KeyboardType.Text }),
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None)
}

@Composable
private fun ScreenTitle(text: String, sub: String? = null) {
    Column(Modifier.padding(top = 16.dp, bottom = 4.dp)) {
        Text(text, style = Pal.Title)
        sub?.let { Text(it, style = Pal.Caption) }
    }
}

// ---------------------------------------------------------------- sign in
@Composable
fun AuthScreen(s: AppState) {
    var email by remember { mutableStateOf("") }
    var pw by remember { mutableStateOf("") }
    Column(SCREEN.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        ScreenTitle("FinAssist", "Sign in or create an account")
        PalCard {
            Field("Email", email, { email = it.trim() })
            Field("Password (10+ characters)", pw, { pw = it }, password = true)
            InkButton("Sign in", { s.act({ s.app.api.login(email, pw) }) { pw = ""; s.checkIdentity() } }, busy = s.busy)
            MintButton("Create account", { s.act({ s.app.api.signup(email, pw); s.app.api.login(email, pw) }) { pw = ""; s.checkIdentity() } },
                enabled = !s.busy)
        }
        Text("Your session is stored encrypted with the Android Keystore. This app never holds an AI service key and never moves money.",
            style = Pal.Caption)
    }
}

// ---------------------------------------------------------------- setup (kept from CP3a, restyled)
@Composable
fun SetupScreen(s: AppState) {
    var income by remember { mutableStateOf("") }
    var nextIncome by remember { mutableStateOf("") }
    var rent by remember { mutableStateOf("") }
    var rentDay by remember { mutableStateOf("1") }
    var balance by remember { mutableStateOf("") }
    var summary by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        s.act({ s.app.api.profile() }) { p ->
            p.obj("income")?.let { income = Money.format(it.long("amount_satang") ?: 0).removePrefix("฿"); nextIncome = it.str("next_income_date") ?: "" }
        }
    }
    PalCard {
        Text("Money basics", style = Pal.CardTitle)
        Field("Income per month (฿)", income, { income = it }, number = true)
        Field("Next pay date (YYYY-MM-DD)", nextIncome, { nextIncome = it.trim() })
        Field("Rent or fixed essential (฿, optional)", rent, { rent = it }, number = true)
        Field("Rent due day of month", rentDay, { rentDay = it.filter(Char::isDigit) }, number = true)
        Field("Balance of your main account (฿)", balance, { balance = it }, number = true)
        InkButton("Save", {
            val inc = Money.parseThb(income); val bal = Money.parseThb(balance); val r = if (rent.isBlank()) null else Money.parseThb(rent)
            if (inc == null || bal == null || (rent.isNotBlank() && r == null) || !Regex("""\d{4}-\d{2}-\d{2}""").matches(nextIncome)) {
                s.message = "Check the amounts (e.g. 20,000 or 1234.50) and the date (YYYY-MM-DD)."; return@InkButton
            }
            s.act({
                val api = s.app.api
                val ess = if (r != null && r > 0) listOf(mapOf("name" to "Rent", "amount_satang" to r, "due_day" to (rentDay.toLongOrNull() ?: 1L).coerceIn(1, 31))) else emptyList()
                api.putProfile(inc, "monthly", nextIncome, ess)
                api.addBalance(api.accounts().first().str("id")!!, bal)
                api.plan()
            }) { plan ->
                val cf = plan.obj("cashflow")
                // Signed formatting: a shortage must never read as money available (Codex finding 2).
                summary = "Saved. Until next pay: ${MoneyText.safeToSpend(cf?.long("discretionary_satang") ?: 0)}" +
                        ", ${MoneyText.amount(cf?.long("daily_allowance_satang") ?: 0)} a day."
            }
        }, busy = s.busy)
        summary?.let { HintPill(it) }
    }
}

// ---------------------------------------------------------------- consent: three separate switches (R1.3, R9.6)
@Composable
fun ConsentScreen(s: AppState) {
    var state by remember { mutableStateOf<Load<Set<String>>>(Load.Loading) }
    var scanFrom by remember { mutableStateOf("2026-07-01") }
    val scope = rememberCoroutineScope()
    fun reload() = s.load({ s.app.api.activeConsentScopes() }) { state = it }
    LaunchedEffect(Unit) { reload() }
    LoadBox(state, ::reload) { active ->
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            PalCard {
                Text("1 · Phone photo permission", style = Pal.CardTitle)
                Text("Not asked in this version. You pick photos with the system photo picker, which shares only the photos you pick.", style = Pal.Body)
            }
            PalCard(flagged = "photo_processing" !in active) {
                Text("2 · Process the photos you send", style = Pal.CardTitle)
                HintPill(if ("photo_processing" in active) "Allowed" else "Not allowed — nothing is sent until you allow it",
                    soft = if ("photo_processing" in active) Pal.MintSoft else Pal.Bg)
                Text("Each photo you send goes to our server and is read by an AI extraction service (Anthropic) to fill in the details.", style = Pal.Caption)
                Field("Only photos taken from (YYYY-MM-DD)", scanFrom, { scanFrom = it.trim() })
                if ("photo_processing" !in active) InkButton("Allow", {
                    s.act({ s.app.api.grantConsent("photo_processing", "v1", mapOf("scan_from" to scanFrom)) }) {
                        scope.launch { s.withReadyQueue { it.resume() }; s.pumpQueue() }; reload()
                    }
                }, busy = s.busy)
                else SoftButton("Withdraw", {
                    s.app.queue.requestPause(BlockReason.CONSENT_REQUIRED) // stop before the next image, now
                    s.act({ s.app.api.revokeConsent("photo_processing") }) { r ->
                        s.pauseQueue(BlockReason.CONSENT_REQUIRED)
                        s.message = "Photo processing stopped. The server cancelled ${r.long("jobs_cancelled") ?: 0} queued job(s)."; reload()
                    }
                }, enabled = !s.busy)
            }
            PalCard {
                Text("3 · Save clear slips automatically", style = Pal.CardTitle)
                Text("If off, every slip waits for you in Review before it is recorded.", style = Pal.Caption)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(checked = "auto_import" in active, enabled = !s.busy, onCheckedChange = { on ->
                        s.act({ if (on) s.app.api.grantConsent("auto_import", "v1") else s.app.api.revokeConsent("auto_import") }) { reload() }
                    })
                    Text(if ("auto_import" in active) "  On" else "  Off", style = Pal.Body)
                }
            }
        }
    }
}

// ---------------------------------------------------------------- upload (Photo Picker → owner-bound queue)
private data class Picked(val bytes: ByteArray?, val mime: String?, val takenIso: String?, val problem: String?)

private fun readPicked(ctx: Context, uri: Uri): Picked {
    val mime = ctx.contentResolver.getType(uri)
    val size = try { ctx.contentResolver.openAssetFileDescriptor(uri, "r")?.use { it.length } ?: -1L } catch (e: Exception) { -1L }
    // Check type and size before reading the file into memory (same limits as the backend).
    if (size > 0) UploadLimits.problem(size, mime)?.let { return Picked(null, mime, null, it) }
    else if (mime !in UploadLimits.ACCEPTED_MIME) return Picked(null, mime, null, "Not a JPG or PNG photo")
    val taken = try {
        ctx.contentResolver.query(uri, arrayOf(MediaStore.MediaColumns.DATE_TAKEN), null, null, null)?.use { c ->
            if (c.moveToFirst() && !c.isNull(0)) Instant.ofEpochMilli(c.getLong(0)).atZone(BKK).toOffsetDateTime().toString() else null
        }
    } catch (e: Exception) { null } // not every provider exposes DATE_TAKEN; the user is then asked about the undated photo
    val bytes = try { ctx.contentResolver.openInputStream(uri)?.use { it.readBytes() } } catch (e: Exception) { null }
        ?: return Picked(null, mime, taken, "Could not read the photo")
    UploadLimits.problem(bytes.size.toLong(), mime)?.let { return Picked(null, mime, taken, it) }
    return Picked(bytes, mime, taken, null)
}

private fun statusTone(e: QueueEntry): Boolean = // true = needs attention (dark outline)
    e.state == LocalState.FAILED || e.state == LocalState.GAVE_UP || e.serverStatus in setOf("needs_review", "extract_failed")

@Composable
fun UploadScreen(s: AppState, openReview: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val entries = remember { mutableStateListOf<QueueEntry>() }
    var blocked by remember { mutableStateOf<BlockReason?>(null) }
    var undated by remember { mutableStateOf<List<Picked>>(emptyList()) }
    LaunchedEffect(s.queueTick) {
        // Only the confirmed account's entries (empty unless the session is Ready).
        val (e, b) = s.onQueue { s.app.gate.visibleEntries() to s.app.gate.readyQueue()?.blocked }
        entries.clear(); entries.addAll(e.sortedByDescending { it.createdAtMs }); blocked = b
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(10)) { uris ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        scope.launch {
            val problems = mutableListOf<String>()
            val noDate = mutableListOf<Picked>()
            for (u in uris) {
                val p = withContext(Dispatchers.IO) { readPicked(ctx, u) }
                if (p.bytes == null) { problems += p.problem ?: "unreadable"; continue }
                if (p.takenIso == null) { noDate += p; continue }
                if (s.withReadyQueue { it.enqueue(p.bytes, p.mime!!, p.takenIso) } == null) { problems += "account not confirmed"; break }
            }
            if (problems.isNotEmpty()) s.message = "Skipped ${problems.size}: ${problems.distinct().joinToString()}"
            undated = noDate
            s.touchQueue(); s.pumpQueue()
        }
    }
    if (undated.isNotEmpty()) {
        AlertDialog(
            onDismissRequest = { undated = emptyList() },
            title = { Text("${undated.size} photo(s) have no date") },
            text = { Text("The app cannot check them against the date range you allowed. Send these photos anyway?") },
            confirmButton = { InkButton("Send these photos", {
                val list = undated; undated = emptyList()
                scope.launch {
                    for (p in list) s.withReadyQueue { it.enqueue(p.bytes!!, p.mime!!, null, confirmedUndated = true) }
                    s.touchQueue(); s.pumpQueue()
                }
            }) },
            dismissButton = { SoftButton("Don't send", { undated = emptyList() }) })
    }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 18.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            ScreenTitle("Upload", "Only the photos you choose are sent. JPG or PNG, up to 8 MB.")
        }
        item {
            InkButton("Upload slip photos", { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) })
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SoftButton("Refresh", { s.pumpQueue() })
                if (blocked == BlockReason.PAUSED_BY_USER) SoftButton("Resume", { scope.launch { s.withReadyQueue { it.resume() }; s.pumpQueue() } })
                else SoftButton("Pause sending", { s.pauseQueue(BlockReason.PAUSED_BY_USER) })
            }
        }
        blocked?.let { b -> item {
            HintPill(when (b) {
                BlockReason.CONSENT_REQUIRED -> "Sending stopped: photo processing is not allowed (see You → Consent)"
                BlockReason.PAUSED_BY_USER -> "Paused — nothing is sent until you resume"
                BlockReason.SIGNED_OUT -> "Sending stopped: sign in again"
            }, soft = Pal.Bg)
        } }
        if (entries.isEmpty()) item { Text("No photos on this phone waiting or sent in this session.", style = Pal.Caption) }
        items(entries, key = { it.sha256 }) { e ->
            PalCard(flagged = statusTone(e)) {
                Text(UploadLabels.label(e, blocked), style = Pal.CardTitle)
                Text("photo ${e.sha256.take(8)} · ${e.capturedAt?.take(10) ?: "no date"}" + (if (e.attempts > 1) " · tries ${e.attempts}" else ""),
                    style = Pal.Caption)
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (e.serverStatus == "needs_review") SoftButton("Open review", openReview)
                    if (UploadLabels.canRetryServer(e)) SoftButton("Retry processing", {
                        s.act({ s.app.api.retryUpload(e.uploadId!!) }) { scope.launch { s.withReadyQueue { it.markServerRetried(e.sha256) }; s.pumpQueue() } }
                    })
                    if (UploadLabels.needsUndatedConfirmation(e)) SoftButton("Send without date", {
                        scope.launch { s.withReadyQueue { it.confirmUndated(e.sha256) }; s.pumpQueue() }
                    })
                    if (UploadLabels.canRetryLocal(e)) SoftButton("Retry upload", { scope.launch { s.withReadyQueue { it.retryLocal(e.sha256) }; s.pumpQueue() } })
                    if (e.state == LocalState.FAILED || e.state == LocalState.GAVE_UP)
                        SoftButton("Discard", { scope.launch { s.withReadyQueue { it.forget(e.sha256) }; s.touchQueue() } })
                }
            }
        }
    }
}

// ---------------------------------------------------------------- review list + review sheet (pocket-pal variant A)
@Composable
fun ReviewScreen(s: AppState, openId: String?, onOpened: () -> Unit) {
    var state by remember { mutableStateOf<Load<List<ReviewView>>>(Load.Loading) }
    var open by remember { mutableStateOf<ReviewView?>(null) }
    fun reload() = s.load({ s.app.api.reviewItems().list("items").objs().map { ReviewView(it) } }) { st ->
        state = st
        if (st is Load.Ready) {
            open = open?.let { o -> st.value.firstOrNull { it.id == o.id } } // the open item closes if it is no longer waiting
            if (openId != null) { st.value.firstOrNull { it.id == openId }?.let { open = it }; onOpened() }
        }
    }
    LaunchedEffect(openId) { reload() }
    val current: ReviewView? = open
    if (current != null) { ReviewSheet(s, current, close = { open = null }, afterDecision = { reload() }); return }
    Column(SCREEN.fillMaxSize().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ScreenTitle("Review", "Items here are not counted in your totals until you decide.")
        Row { SoftButton("Refresh", { reload() }) }
        LoadBox(state, ::reload) { items ->
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (items.isEmpty()) HintPill("Nothing is waiting for you.")
                items.forEach { v ->
                    PalCard(onClick = { open = v }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(v.title, style = Pal.CardTitle, modifier = Modifier.weight(1f))
                            Tag(if (v.reason == "possible_duplicate") "Possible duplicate" else "Needs review")
                        }
                        Text(listOfNotNull(v.extracted.str("payee"), v.amountReadSatang?.let { "${MoneyText.magnitude(it)} as read" } ?: "amount unreadable",
                            v.extracted.str("date_text")).joinToString(" · "), style = Pal.Caption)
                    }
                }
            }
        }
    }
}

@Composable
private fun ReviewSheet(s: AppState, v: ReviewView, close: () -> Unit, afterDecision: () -> Unit) {
    val edited = remember(v.id) { mutableStateMapOf<String, String>().apply { putAll(v.initialInputs()) } }
    var chosen by remember(v.id) { mutableStateOf<String?>(null) }
    var photo by remember(v.id) { mutableStateOf<Load<ImageBitmap?>>(Load.Loading) }
    var zoom by remember(v.id) { mutableStateOf(false) }
    var recordedTxn by remember(v.id) { mutableStateOf<String?>(null) }
    fun loadPhoto() = s.load({
        v.uploadId?.let { id -> s.app.api.uploadImage(id).let { b -> BitmapFactory.decodeByteArray(b, 0, b.size)?.asImageBitmap() } }
    }) { photo = it }
    LaunchedEffect(v.id) { loadPhoto() }
    if (recordedTxn != null) { PocketChooser(s, recordedTxn!!, done = { recordedTxn = null; close(); afterDecision() }); return }
    Column(SCREEN.fillMaxSize().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Check your ${when (v.docType) { "receipt" -> "receipt"; "bill" -> "bill"; else -> "slip" }}", style = Pal.Title, modifier = Modifier.weight(1f))
            SoftButton("Close", close)
        }
        // Photo first, so the user compares against what is printed. Memory only; never written to disk.
        LoadBox(photo, ::loadPhoto) { bmp ->
            if (bmp == null) HintPill("No photo available", soft = Pal.Bg)
            else Box(Modifier.fillMaxWidth().background(Pal.Line, Pal.CtlShape).clickable { zoom = !zoom }) {
                Image(bmp, contentDescription = "Your uploaded photo", modifier = Modifier.fillMaxWidth().height(if (zoom) 420.dp else 160.dp),
                    contentScale = ContentScale.Fit)
            }
        }
        if (v.reason == "possible_duplicate" || v.reason == "receipt_link") PalCard(flagged = true) {
            Text(if (v.reason == "receipt_link") "This looks like the receipt of a payment you already have." else "This looks like a payment you already have.",
                style = Pal.CardTitle)
            Text("Saving it as new would count the money twice. Pick the matching record below if it is the same.", style = Pal.Caption)
        }
        // Every input the server needs for this item (finding 1); choices are never pre-selected for the user.
        val shown = v.inputs(edited)
        if ("doc_type" in shown) ChoiceCard("What is this document?", "doc_type", ReviewView.TYPE_CHOICES, v, edited)
        FieldCard("Amount (as printed)", "amount_text", v, edited, number = true)
        FieldCard(if (v.effectiveType(edited) == "bill") "Issue date (as printed)" else "Date (as printed)", "date_text", v, edited)
        FieldCard("Time", "time_text", v, edited)
        FieldCard(if (v.effectiveType(edited) == "transfer_in") "Received from" else "Paid to", "payee", v, edited)
        if ("due_date_text" in shown) FieldCard("Due date (as printed)", "due_date_text", v, edited)
        if ("status" in shown) ChoiceCard("Did this payment go through?", "status", ReviewView.STATUS_CHOICES, v, edited)
        val missing = v.missingRequired(edited)
        if (missing.isNotEmpty() && v.actions.any { it.decision == "accept" || it.decision == "distinct" })
            Text("Fill in the marked details to save.", style = Pal.Caption)
        if (v.candidates.isNotEmpty()) PalCard {
            Text("Existing record(s)", style = Pal.CardTitle)
            v.candidates.forEach { c ->
                Row(Modifier.fillMaxWidth().clickable { chosen = c.txnId }, verticalAlignment = Alignment.CenterVertically) {
                    val selected = (chosen ?: v.candidates.singleOrNull()?.txnId) == c.txnId
                    RadioButton(selected = selected, onClick = { chosen = c.txnId })
                    Text(listOfNotNull(c.amountSatang?.let { MoneyText.magnitude(it) }, c.date, c.payee, c.source).joinToString(" · "), style = Pal.Body)
                }
            }
        }
        // Exactly the decisions the server allows for this item (allowed_decisions); nothing is decided locally.
        PalCard {
            v.actions.forEachIndexed { i, a ->
                val run = { s.resolve(v, a, edited.toMap(), chosen) { o ->
                    when {
                        o is ResolveOutcome.Done && o.txnId != null && a.decision in setOf("accept", "distinct") -> { recordedTxn = o.txnId }
                        o.isSuccess -> { close(); afterDecision() }
                        else -> afterDecision() // 404, 409, lost response…: reload; never shown as saved
                    }
                } }
                if (i == 0) InkButton(a.label, run, enabled = v.canRun(a, chosen, edited), busy = s.busy)
                else SoftButton(a.label, run, Modifier.fillMaxWidth(), enabled = !s.busy && v.canRun(a, chosen, edited))
            }
            if (v.actions.isEmpty()) Text("This app version does not know the decisions offered for this item. Nothing can be done here.", style = Pal.Caption)
        }
    }
}

@Composable
private fun ChoiceCard(label: String, key: String, choices: List<ReviewView.Choice>, v: ReviewView, edited: MutableMap<String, String>) {
    val empty = (edited[key] ?: "").isBlank()
    PalCard(flagged = v.flagged(key) && empty) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = Pal.Caption, modifier = Modifier.weight(1f))
            if (empty) Tag("Needed")
        }
        choices.forEach { c ->
            Row(Modifier.fillMaxWidth().clickable { edited[key] = c.value }, verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected = edited[key] == c.value, onClick = { edited[key] = c.value })
                Text(c.label, style = Pal.Body)
            }
        }
    }
}

@Composable
private fun FieldCard(label: String, key: String, v: ReviewView, edited: MutableMap<String, String>, number: Boolean = false) {
    val unsure = v.flagged(key) && edited[key] == (v.extracted.str(key) ?: "")
    PalCard(flagged = unsure) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = Pal.Caption, modifier = Modifier.weight(1f))
            if (unsure) Tag(if ((v.extracted.str(key) ?: "").isBlank()) "Needed" else "Check this")
        }
        Field("", edited[key] ?: "", { edited[key] = it }, number = number)
    }
}

/** After a decision recorded a transaction: optional pocket (category) choice. Skipping is fine. */
@Composable
private fun PocketChooser(s: AppState, txnId: String, done: () -> Unit) {
    var pockets by remember { mutableStateOf<Load<List<Map<String, Any?>>>>(Load.Loading) }
    fun reload() = s.load({ s.app.api.pockets() }) { pockets = it }
    LaunchedEffect(txnId) { reload() }
    Column(SCREEN.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ScreenTitle("Recorded", "Which pocket is it? (optional)")
        LoadBox(pockets, ::reload) { list ->
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                list.forEach { p ->
                    val cats = p.list("categories").map { it.toString() }
                    val cat = if ("other" in cats) "other" else cats.firstOrNull()
                    if (cat != null) SoftButton(p.str("name") ?: cat, {
                        s.act({ s.app.api.setCategory(txnId, cat, setDefault = false) }) { done() }
                    }, Modifier.fillMaxWidth(), enabled = !s.busy)
                }
            }
        }
        InkButton("Skip", done)
    }
}

// ---------------------------------------------------------------- activity (pocket-pal Activity layout, real data)
private data class ActivityData(val screen: ActivityModel.Screen)

@Composable
fun ActivityScreen(s: AppState, openReview: (String) -> Unit) {
    var state by remember { mutableStateOf<Load<ActivityData>>(Load.Loading) }
    var filter by remember { mutableStateOf("All") }
    fun reload(quiet: Boolean = false) = s.load({
        val api = s.app.api
        ActivityData(ActivityModel.build(api.transactions(), api.reviewItems().list("items").objs(), api.bills("unpaid"), api.pockets(),
            LocalDate.now(BKK)))
    }, quiet) { state = it }
    LaunchedEffect(Unit) { reload() }
    LaunchedEffect(s.queueTick) { if (state is Load.Ready) reload(quiet = true) } // queue progress: refresh without flicker
    Column(SCREEN.fillMaxSize().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) { ScreenTitle("Activity") }
            SoftButton("Refresh", { reload() })
        }
        LoadBox(state, { reload() }) { data ->
            val sc = data.screen
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                if (sc.bills.isNotEmpty() && filter == "All") PalCard {
                    Text("Upcoming bills", style = Pal.CardTitle)
                    sc.bills.forEach { b ->
                        Row {
                            Column(Modifier.weight(1f)) {
                                Text(b.biller, style = Pal.Body.copy(fontWeight = FontWeight.Bold))
                                Text("Due ${b.due}" + when { b.daysUntil > 1 -> " · in ${b.daysUntil} days"; b.daysUntil == 1L -> " · tomorrow"
                                    b.daysUntil == 0L -> " · today"; else -> " · ${-b.daysUntil} days ago" }, style = Pal.Caption)
                            }
                            Text(MoneyText.magnitude(b.amountSatang), style = Pal.Amount)
                        }
                    }
                }
                val filters = listOf("All", "Waiting (${sc.waiting.size})") + sc.pocketFilters
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    filters.forEach { f -> Chip(f, filter == f || (f.startsWith("Waiting") && filter == "Waiting")) {
                        filter = if (f.startsWith("Waiting")) "Waiting" else f } }
                }
                if (sc.waiting.isNotEmpty() && filter != "Waiting")
                    Text("${sc.waiting.size} item(s) need a quick check. They aren't counted in your totals yet.", style = Pal.Caption)
                if (filter == "All" || filter == "Waiting") {
                    if (sc.waiting.isNotEmpty()) PalCard {
                        Text("Waiting for you", style = Pal.CardTitle)
                        sc.waiting.forEach { r -> ActivityRow(r) { r.reviewId?.let(openReview) } }
                    }
                }
                if (filter != "Waiting") {
                    val days = sc.days.map { d -> d to (if (filter == "All") d.rows else d.rows.filter { it.pocket == filter }) }.filter { it.second.isNotEmpty() }
                    if (days.isEmpty() && sc.waiting.isEmpty()) HintPill("No transactions yet. Upload a slip to start.", soft = Pal.Bg)
                    days.forEach { (d, rows) ->
                        PalCard {
                            Row {
                                Text(d.label, style = Pal.CardTitle, modifier = Modifier.weight(1f))
                                if (filter == "All" && d.outSatang > 0) Text("out ${MoneyText.magnitude(d.outSatang)}", style = Pal.Caption)
                            }
                            rows.forEach { r -> ActivityRow(r, null) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ActivityRow(r: ActivityModel.Row, onClick: (() -> Unit)?) {
    Row(Modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it }.padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(r.title, style = Pal.Body.copy(fontWeight = FontWeight.Bold))
            Text(listOfNotNull(r.pocket ?: if (r.reviewId == null) "No pocket yet" else null, r.source).joinToString(" · "), style = Pal.Caption)
            if (r.tags.isNotEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { r.tags.forEach { Tag(it) } }
        }
        val amt = r.amountSatang
        Text(when {
            amt == null -> "amount ?"
            r.reviewId != null -> MoneyText.magnitude(amt) + " as read"
            else -> MoneyText.signed(amt, r.moneyIn)
        }, style = Pal.Amount.copy(color = when { !r.counted -> Pal.Muted; r.moneyIn -> Pal.MintText; else -> Pal.Ink }))
    }
}
