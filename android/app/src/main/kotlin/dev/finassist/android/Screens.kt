package dev.finassist.android

import android.content.Context
import android.net.Uri
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import dev.finassist.core.LocalState
import dev.finassist.core.Money
import dev.finassist.core.QueueEntry
import dev.finassist.core.ReviewActions
import dev.finassist.core.UploadLabels
import dev.finassist.core.list
import dev.finassist.core.long
import dev.finassist.core.obj
import dev.finassist.core.objs
import dev.finassist.core.str
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.ZoneId

private val PAD = Modifier.padding(12.dp)

@Composable
private fun Field(label: String, value: String, onChange: (String) -> Unit, number: Boolean = false, password: Boolean = false) {
    OutlinedTextField(value, onChange, label = { Text(label) }, singleLine = true, modifier = Modifier.fillMaxWidth(),
        keyboardOptions = KeyboardOptions(keyboardType = when { password -> KeyboardType.Password; number -> KeyboardType.Decimal; else -> KeyboardType.Text }),
        visualTransformation = if (password) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None)
}

// ---------------------------------------------------------------- auth
@Composable
fun AuthScreen(s: AppState) {
    var email by remember { mutableStateOf("") }
    var pw by remember { mutableStateOf("") }
    Column(PAD.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Sign in", fontWeight = FontWeight.Bold)
        Field("Email", email, { email = it.trim() })
        Field("Password (10+ characters)", pw, { pw = it }, password = true)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(enabled = !s.busy, onClick = { s.act({ s.app.api.login(email, pw) }) { pw = ""; s.signedInNow() } }) { Text("Sign in") }
            OutlinedButton(enabled = !s.busy, onClick = {
                s.act({ s.app.api.signup(email, pw); s.app.api.login(email, pw) }) { pw = ""; s.signedInNow() }
            }) { Text("Create account") }
        }
        Text("The session token is stored encrypted with the Android Keystore. The assistant's model key never reaches this app.")
    }
}

// ---------------------------------------------------------------- setup (R1.2)
private val DEFAULT_POCKETS = listOf("Food" to listOf("food"), "Transport" to listOf("transport"), "Shopping" to listOf("shopping"),
    "Entertainment" to listOf("entertainment"), "Other" to listOf("other", "bills"))

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
    Column(PAD.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Your money basics (monthly income)", fontWeight = FontWeight.Bold)
        Field("Income per month (THB)", income, { income = it }, number = true)
        Field("Next pay date (YYYY-MM-DD)", nextIncome, { nextIncome = it.trim() })
        Field("Rent / fixed essential (THB, optional)", rent, { rent = it }, number = true)
        Field("Rent due day of month", rentDay, { rentDay = it.filter(Char::isDigit) }, number = true)
        Field("Current balance of your main account (THB)", balance, { balance = it }, number = true)
        Button(enabled = !s.busy, onClick = {
            val inc = Money.parseThb(income); val bal = Money.parseThb(balance); val r = if (rent.isBlank()) null else Money.parseThb(rent)
            if (inc == null || bal == null || (rent.isNotBlank() && r == null) || !Regex("""\d{4}-\d{2}-\d{2}""").matches(nextIncome)) {
                s.message = "Check the amounts (e.g. 20,000 or 1234.50) and the date (YYYY-MM-DD)."; return@Button
            }
            s.act({
                val api = s.app.api
                val ess = if (r != null && r > 0) listOf(mapOf("name" to "Rent", "amount_satang" to r, "due_day" to (rentDay.toLongOrNull() ?: 1L).coerceIn(1, 31))) else emptyList()
                api.putProfile(inc, "monthly", nextIncome, ess)
                api.addBalance(api.accounts().first().str("id")!!, bal)
                if (api.pockets().isEmpty()) DEFAULT_POCKETS.forEach { (n, c) -> api.createPocket(n, c) }
                api.plan()
            }) { plan ->
                val cf = plan.obj("cashflow")
                summary = "Saved. Money left until next pay: ${Money.format(cf?.long("discretionary_satang") ?: 0)}; " +
                        "per day ${Money.format(cf?.long("daily_allowance_satang") ?: 0)}."
            }
        }) { Text("Save") }
        summary?.let { Text(it) }
    }
}

// ---------------------------------------------------------------- consent (R1.3, R9.6): three separate things
@Composable
fun ConsentScreen(s: AppState) {
    var active by remember { mutableStateOf<Set<String>>(emptySet()) }
    var scanFrom by remember { mutableStateOf("2026-07-01") }
    val scope = rememberCoroutineScope()
    fun reload() = s.act({ s.app.api.activeConsentScopes() }) { active = it }
    LaunchedEffect(Unit) { reload() }
    Column(PAD.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Card { Column(PAD) {
            Text("1. Phone photo permission (Android)", fontWeight = FontWeight.Bold)
            Text("Not requested in this version. Choosing photos yourself uses the system photo picker, which shares only the photos you pick. " +
                    "Automatic album scanning comes in the next checkpoint and will ask separately.")
        } }
        Card { Column(PAD) {
            Text("2. Allow the service to process the photos you send", fontWeight = FontWeight.Bold)
            Text(if ("photo_processing" in active) "Allowed" else "Not allowed — uploads are refused by the server")
            Field("Only photos taken from (YYYY-MM-DD)", scanFrom, { scanFrom = it.trim() })
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(enabled = !s.busy && "photo_processing" !in active, onClick = {
                    s.act({ s.app.api.grantConsent("photo_processing", "v1", mapOf("scan_from" to scanFrom)) }) {
                        scope.launch { s.onQueue { s.app.queue.resume() }; s.pumpQueue() }; reload()
                    }
                }) { Text("Allow") }
                OutlinedButton(enabled = !s.busy && "photo_processing" in active, onClick = {
                    s.app.queue.requestPause(dev.finassist.core.BlockReason.CONSENT_REQUIRED) // stop before the next image, now
                    s.act({ s.app.api.revokeConsent("photo_processing") }) { r ->
                        // Nothing new is sent after revocation; the server has cancelled queued work.
                        s.pauseQueue(dev.finassist.core.BlockReason.CONSENT_REQUIRED)
                        s.message = "Photo processing stopped. Server cancelled ${r.long("jobs_cancelled") ?: 0} queued job(s)."; reload()
                    }
                }) { Text("Withdraw") }
            }
        } }
        Card { Column(PAD) {
            Text("3. Save clear slips automatically", fontWeight = FontWeight.Bold)
            Text("If off, every slip waits for you in Review before it is recorded.")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Switch(checked = "auto_import" in active, enabled = !s.busy, onCheckedChange = { on ->
                    s.act({ if (on) s.app.api.grantConsent("auto_import", "v1") else s.app.api.revokeConsent("auto_import") }) { reload() }
                })
                Text(if ("auto_import" in active) "  On" else "  Off")
            }
        } }
    }
}

// ---------------------------------------------------------------- manual upload (fallback) + status + retry
private data class Picked(val bytes: ByteArray?, val mime: String?, val takenIso: String?, val problem: String?)

private fun readPicked(ctx: Context, uri: Uri, maxBytes: Int = 8 * 1024 * 1024): Picked {
    val mime = ctx.contentResolver.getType(uri)
    if (mime != "image/jpeg" && mime != "image/png") return Picked(null, mime, null, "unsupported format ($mime); JPEG or PNG only")
    val taken = try {
        ctx.contentResolver.query(uri, arrayOf(MediaStore.MediaColumns.DATE_TAKEN), null, null, null)?.use { c ->
            if (c.moveToFirst() && !c.isNull(0)) Instant.ofEpochMilli(c.getLong(0)).atZone(ZoneId.of("Asia/Bangkok")).toOffsetDateTime().toString() else null
        }
    } catch (e: Exception) { null } // not every provider exposes DATE_TAKEN; the server then cannot apply the date range to this photo
    val bytes = ctx.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return Picked(null, mime, taken, "could not read")
    if (bytes.size > maxBytes) return Picked(null, mime, taken, "larger than 8 MB")
    return Picked(bytes, mime, taken, null)
}

@Composable
fun UploadScreen(s: AppState) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val entries = remember { mutableStateListOf<QueueEntry>() }
    var blocked by remember { mutableStateOf<dev.finassist.core.BlockReason?>(null) }
    var serverInfo by remember { mutableStateOf("") }
    LaunchedEffect(s.queueTick) {
        val (e, b) = s.onQueue { s.app.queue.snapshot() to s.app.queue.blocked }
        entries.clear(); entries.addAll(e.sortedByDescending { it.createdAtMs }); blocked = b
    }
    LaunchedEffect(Unit) {
        s.act({ s.app.api.scanStatus() }) { st -> serverInfo = "Server: processing ${if (st["processing_allowed"] == true) "allowed" else "NOT allowed"}" }
    }
    // Photos without a capture date cannot be checked against the consented date range: ask about them explicitly.
    var undated by remember { mutableStateOf<List<Picked>>(emptyList()) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(10)) { uris ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        scope.launch {
            val problems = mutableListOf<String>()
            val noDate = mutableListOf<Picked>()
            for (u in uris) {
                val p = withContext(Dispatchers.IO) { readPicked(ctx, u) }
                if (p.bytes == null) { problems += p.problem ?: "unreadable"; continue }
                if (p.takenIso == null) { noDate += p; continue }
                s.onQueue { s.app.queue.enqueue(p.bytes, p.mime!!, p.takenIso) }
            }
            if (problems.isNotEmpty()) s.message = "Skipped ${problems.size}: ${problems.distinct().joinToString()}"
            undated = noDate
            s.touchQueue(); s.pumpQueue()
        }
    }
    if (undated.isNotEmpty()) {
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { undated = emptyList<Picked>() },
            title = { Text("${undated.size} photo(s) have no date") },
            text = { Text("The app cannot check them against the date range you allowed. Send these photos anyway?") },
            confirmButton = { Button(onClick = {
                val list = undated; undated = emptyList<Picked>()
                scope.launch {
                    for (p in list) s.onQueue { s.app.queue.enqueue(p.bytes!!, p.mime!!, null, confirmedUndated = true) }
                    s.touchQueue(); s.pumpQueue()
                }
            }) { Text("Send these photos") } },
            dismissButton = { OutlinedButton(onClick = { undated = emptyList<Picked>() }) { Text("Don't send") } })
    }
    Column(Modifier.fillMaxSize()) {
        Column(PAD, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Button(onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }) { Text("Choose slip photos") }
            Text("Only the photos you choose are sent. $serverInfo")
            blocked?.let { Text("Sending is stopped: $it", fontWeight = FontWeight.Bold) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { s.pumpQueue() }) { Text("Refresh") }
                if (blocked == dev.finassist.core.BlockReason.PAUSED_BY_USER)
                    OutlinedButton(onClick = { scope.launch { s.onQueue { s.app.queue.resume() }; s.pumpQueue() } }) { Text("Resume") }
                else OutlinedButton(onClick = { s.pauseQueue(dev.finassist.core.BlockReason.PAUSED_BY_USER) }) { Text("Pause sending") }
            }
        }
        HorizontalDivider()
        LazyColumn(Modifier.fillMaxSize()) {
            items(entries, key = { it.sha256 }) { e ->
                Column(PAD) {
                    Text(UploadLabels.label(e, blocked), fontWeight = FontWeight.Bold)
                    Text("photo ${e.sha256.take(8)} · ${e.capturedAt ?: "date unknown"}" + (if (e.attempts > 1) " · tries ${e.attempts}" else ""))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (UploadLabels.canRetryServer(e)) OutlinedButton(onClick = {
                            s.act({ s.app.api.retryUpload(e.uploadId!!) }) { scope.launch { s.onQueue { s.app.queue.markServerRetried(e.sha256) }; s.pumpQueue() } }
                        }) { Text("Retry processing") }
                        if (UploadLabels.needsUndatedConfirmation(e)) OutlinedButton(onClick = {
                            scope.launch { s.onQueue { s.app.queue.confirmUndated(e.sha256) }; s.pumpQueue() }
                        }) { Text("Send without date") }
                        if (UploadLabels.canRetryLocal(e)) OutlinedButton(onClick = {
                            scope.launch { s.onQueue { s.app.queue.retryLocal(e.sha256) }; s.pumpQueue() }
                        }) { Text("Retry upload") }
                        if (e.state == LocalState.FAILED || e.state == LocalState.GAVE_UP) OutlinedButton(onClick = {
                            scope.launch { s.onQueue { s.app.queue.forget(e.sha256) }; s.touchQueue() }
                        }) { Text("Discard") }
                    }
                }
                HorizontalDivider()
            }
        }
    }
}

// ---------------------------------------------------------------- review (R2.6)
@Composable
fun ReviewScreen(s: AppState) {
    var items by remember { mutableStateOf<List<Map<String, Any?>>>(emptyList()) }
    fun reload() = s.act({ s.app.api.reviewItems().list("items").objs() }) { items = it }
    LaunchedEffect(Unit) { reload() }
    LazyColumn(Modifier.fillMaxSize()) {
        item { Row(PAD) { Text("${items.size} item(s) need you", Modifier.weight(1f)); OutlinedButton(onClick = { reload() }) { Text("Refresh") } } }
        items(items, key = { it.str("id")!! }) { it -> ReviewCard(s, it) { reload(); s.pumpQueue() } }
    }
}

@Composable
private fun ReviewCard(s: AppState, item: Map<String, Any?>, done: () -> Unit) {
    val ex = item.obj("extracted") ?: emptyMap()
    var amount by remember { mutableStateOf(ex.str("amount_text") ?: "") }
    var date by remember { mutableStateOf(ex.str("date_text") ?: "") }
    var time by remember { mutableStateOf(ex.str("time_text") ?: "") }
    var payee by remember { mutableStateOf(ex.str("payee") ?: "") }
    val reason = item.str("reason")
    Card(Modifier.padding(8.dp).fillMaxWidth()) {
        Column(PAD, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(when (reason) {
                "missing_fields" -> "Some details could not be read: ${item.list("problem_fields").joinToString()}"
                "confirm_import" -> "Confirm this ${ex.str("doc_type") ?: "slip"} before it is recorded"
                "possible_duplicate" -> "This may be a payment you already have"
                "receipt_link" -> "This receipt may belong to a payment you already have"
                else -> reason ?: "Review"
            }, fontWeight = FontWeight.Bold)
            Field("Amount (as printed)", amount, { amount = it }, number = true)
            Field("Date (as printed)", date, { date = it })
            Field("Time", time, { time = it })
            Field("Other party", payee, { payee = it })
            val candidates = item.list("candidates").objs()
            candidates.forEach { c ->
                Text("Existing record: ${Money.format(c.long("amount_satang") ?: 0)} · ${c.str("occurred_date")} · ${c.str("payee_display") ?: ""} · ${c.str("source")}")
            }
            // Only the decisions the server allows for this item; a receipt or a likely duplicate never gets "record as new".
            ReviewActions.forItem(item).forEach { a ->
                OutlinedButton(enabled = !s.busy && (!a.needsCandidate || candidates.size == 1), modifier = Modifier.fillMaxWidth(), onClick = {
                    val changed = linkedMapOf<String, Any?>()
                    if (a.decision == "accept" || a.decision == "distinct") { // only fields the user changed; the server re-validates
                        if (amount != (ex.str("amount_text") ?: "")) changed["amount_text"] = amount
                        if (date != (ex.str("date_text") ?: "")) changed["date_text"] = date
                        if (time != (ex.str("time_text") ?: "")) changed["time_text"] = time.ifBlank { null }
                        if (payee != (ex.str("payee") ?: "")) changed["payee"] = payee
                    }
                    val txnId = if (a.needsCandidate) candidates.single().str("txn_id") else null
                    s.act({ s.app.api.resolveReview(item.str("id")!!, a.decision, changed.ifEmpty { null }, txnId) }) { done() }
                }) { Text(a.label) }
            }
            if (candidates.size > 1) Text("Several possible matches — choosing one is not supported in this version.")
        }
    }
}

// ---------------------------------------------------------------- ledger: money left, pockets, transactions, unclassified
private val CATEGORIES = listOf("food", "transport", "shopping", "entertainment", "bills", "other")

@Composable
fun LedgerScreen(s: AppState) {
    var plan by remember { mutableStateOf<Map<String, Any?>>(emptyMap()) }
    var txns by remember { mutableStateOf<List<Map<String, Any?>>>(emptyList()) }
    var unclassified by remember { mutableStateOf<List<Map<String, Any?>>>(emptyList()) }
    fun reload() = s.act({ Triple(s.app.api.plan(), s.app.api.transactions(), s.app.api.reviewItems().list("uncategorised_payees").objs()) }) {
        plan = it.first; txns = it.second; unclassified = it.third
    }
    LaunchedEffect(Unit) { reload() }
    val cf = plan.obj("cashflow")
    LazyColumn(Modifier.fillMaxSize()) {
        item {
            Column(PAD) {
                Row { Text("Money left until next pay", Modifier.weight(1f), fontWeight = FontWeight.Bold); OutlinedButton(onClick = { reload() }) { Text("Refresh") } }
                Text(Money.format(cf?.long("discretionary_satang") ?: 0) + " · per day " + Money.format(cf?.long("daily_allowance_satang") ?: 0))
                Text("Balance projected from your last balance entry; only detected or entered records are counted.")
                Spacer(Modifier.height(8.dp))
                Text("Pockets", fontWeight = FontWeight.Bold)
                val pockets = plan.list("pockets").objs()
                if (pockets.none { it["pocket_id"] != null }) Text("No budget plan yet (set up in the next checkpoint with the assistant).")
                pockets.forEach { p ->
                    if (p["pocket_id"] == null) Text("Not in any pocket: ${Money.format(p.long("unassigned_satang") ?: 0)}" +
                            " · not counted (pending/unclear): ${p.long("excluded_unresolved_count") ?: 0}")
                    else Text("${p.str("name")}: left ${Money.format(p.long("remaining_satang") ?: 0)} of ${Money.format(p.long("allocation_satang") ?: 0)}" +
                            (if ((p.long("spent_predicted_satang") ?: 0) > 0) " (includes guessed categories)" else ""))
                }
                Spacer(Modifier.height(8.dp))
                Text("Not yet categorised", fontWeight = FontWeight.Bold)
                if (unclassified.isEmpty()) Text("Nothing waiting.")
                unclassified.forEach { g -> Text("${g.str("payee_display") ?: "(unknown)"} · ${g.long("n")} × · ${Money.format(g.long("total_satang") ?: 0)}") }
                Spacer(Modifier.height(8.dp))
                Text("Transactions", fontWeight = FontWeight.Bold)
            }
        }
        items(txns, key = { it.str("id")!! }) { t -> TxnRow(s, t) { reload() } }
    }
}

@Composable
private fun TxnRow(s: AppState, t: Map<String, Any?>, changed: () -> Unit) {
    var open by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
        val sign = if (t.str("kind") in setOf("income", "refund", "transfer_in")) "+" else "−"
        Text("$sign${Money.format(t.long("amount_satang") ?: 0)}  ${t.str("payee_display") ?: ""}", fontWeight = FontWeight.Bold)
        Text("${t.str("occurred_date")} · ${t.str("kind")} · ${t.str("payment_status")} · ${t.str("source")} · " +
                (t.str("category_code")?.let { "$it (${t.str("category_state")})" } ?: "no category"))
        if (t.str("kind") == "expense") {
            OutlinedButton(onClick = { open = !open }) { Text(if (open) "Close" else "Set category") }
            if (open) Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                CATEGORIES.forEach { c -> OutlinedButton(onClick = { s.act({ s.app.api.setCategory(t.str("id")!!, c, setDefault = false) }) { open = false; changed() } }) { Text(c) } }
            }
        }
    }
    HorizontalDivider()
}
