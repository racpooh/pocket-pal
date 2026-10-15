package dev.finassist.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import dev.finassist.core.SessionState

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as FinAssistApp
        setContent {
            MaterialTheme {
                Surface(Modifier.fillMaxSize().safeDrawingPadding()) {
                    val scope = rememberCoroutineScope()
                    val state = remember { AppState(app, scope) }
                    AppRoot(state)
                }
            }
        }
    }
}

private val TABS = listOf("Setup", "Consent", "Upload", "Review", "Ledger")

@Composable
fun AppRoot(s: AppState) {
    LaunchedEffect(Unit) { s.checkServer(); s.checkIdentity() /* stored session? confirm the account before showing anything */ }
    Column(Modifier.fillMaxSize()) {
        // Visible, never silent: the backend says it is running with the fake (test) extractor.
        if (s.testMode == true) Banner("TEST MODE — fake extraction, synthetic fixtures only. Not real data.", Color(0xFFFFE082))
        s.serverError?.let { Banner(it, Color(0xFFFFCDD2)) }
        if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        s.message?.let { m ->
            Row(Modifier.fillMaxWidth().background(Color(0xFFE3F2FD)).padding(8.dp)) {
                Text(m, Modifier.weight(1f))
                TextButton(onClick = { s.message = null }) { Text("OK") }
            }
        }
        when (val st = s.session) {
            is SessionState.SignedOut -> AuthScreen(s)
            is SessionState.Checking -> Text("Checking your account…", Modifier.padding(16.dp))
            is SessionState.IdentityFailed -> Column(Modifier.padding(16.dp)) {
                Text("Your account could not be confirmed (${st.reason}). Photos waiting on this phone stay hidden and are not sent.")
                Row {
                    TextButton(onClick = { s.checkIdentity() }) { Text("Retry") }
                    TextButton(onClick = { s.logout() }) { Text("Log out") }
                }
            }
            is SessionState.Ready -> SignedIn(s)
        }
    }
}

@Composable
private fun SignedIn(s: AppState) {
    Column(Modifier.fillMaxSize()) {
        var tab by rememberSaveable { mutableIntStateOf(0) }
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
            Text("FinAssist CP3a", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f).padding(top = 12.dp))
            TextButton(onClick = { s.logout() }) { Text("Log out") }
        }
        ScrollableTabRow(selectedTabIndex = tab) {
            TABS.forEachIndexed { i, t -> Tab(selected = tab == i, onClick = { tab = i }, text = { Text(t) }) }
        }
        when (tab) {
            0 -> SetupScreen(s)
            1 -> ConsentScreen(s)
            2 -> UploadScreen(s)
            3 -> ReviewScreen(s)
            else -> LedgerScreen(s)
        }
    }
}

@Composable
fun Banner(text: String, color: Color) {
    Text(text, Modifier.fillMaxWidth().background(color).padding(8.dp), fontWeight = FontWeight.Bold)
}
