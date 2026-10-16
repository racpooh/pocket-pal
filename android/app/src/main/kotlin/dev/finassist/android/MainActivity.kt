package dev.finassist.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import dev.finassist.core.SessionState

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as FinAssistApp
        setContent {
            PalTheme {
                Box(Modifier.fillMaxSize().background(Pal.Bg).safeDrawingPadding()) {
                    val scope = rememberCoroutineScope()
                    val state = remember { AppState(app, scope) }
                    AppRoot(state)
                }
            }
        }
    }
}

@Composable
fun AppRoot(s: AppState) {
    LaunchedEffect(Unit) { s.checkServer(); s.checkIdentity() /* stored session? confirm the account before showing anything */ }
    Column(Modifier.fillMaxSize()) {
        // Shown whenever the backend reports test mode (fake extraction). Never silent; never shown otherwise.
        if (s.testMode == true) Text("TEST MODE — fake extraction, synthetic data only", Modifier.fillMaxWidth().background(Pal.TestModeBg)
            .padding(horizontal = 18.dp, vertical = 6.dp), style = Pal.Caption.copy(color = Pal.Ink, fontWeight = FontWeight.Bold))
        s.serverError?.let { err ->
            Row(Modifier.fillMaxWidth().background(Pal.DangerSoft).padding(horizontal = 18.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(err, Modifier.weight(1f), style = Pal.Caption.copy(color = Pal.Danger))
                SoftButton("Retry", { s.checkServer() })
            }
        }
        if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Pal.Ink, trackColor = Pal.Line)
        s.message?.let { m ->
            Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 6.dp).background(Pal.MintSoft, Pal.CtlShape).padding(12.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(m, Modifier.weight(1f), style = Pal.Body)
                Text("OK", Modifier.clickable { s.message = null }.padding(8.dp), style = Pal.Body.copy(fontWeight = FontWeight.Bold))
            }
        }
        when (val st = s.session) {
            is SessionState.SignedOut -> AuthScreen(s)
            is SessionState.Checking -> Text("Checking your account…", Modifier.padding(18.dp), style = Pal.Body)
            is SessionState.IdentityFailed -> Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                PalCard(flagged = true) {
                    Text("Your account could not be confirmed", style = Pal.CardTitle)
                    Text("(${st.reason}) Photos waiting on this phone stay hidden and are not sent.", style = Pal.Body)
                    InkButton("Retry", { s.checkIdentity() })
                    SoftButton("Log out", { s.logout() }, Modifier.fillMaxWidth())
                }
            }
            is SessionState.Ready -> SignedIn(s)
        }
    }
}

private enum class Tab(val label: String) { ACTIVITY("Activity"), UPLOAD("Upload"), REVIEW("Review"), YOU("You") }

@Composable
private fun SignedIn(s: AppState) {
    var tab by rememberSaveable { mutableStateOf(Tab.ACTIVITY) }
    var openReviewId by remember { mutableStateOf<String?>(null) }
    // First run: if photo processing is not allowed yet, start on the consent screen (login → consent → upload …).
    LaunchedEffect(Unit) { s.act({ s.app.api.activeConsentScopes() }) { if ("photo_processing" !in it) tab = Tab.YOU } }
    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f).fillMaxWidth()) {
            when (tab) {
                Tab.ACTIVITY -> ActivityScreen(s) { id -> openReviewId = id; tab = Tab.REVIEW }
                Tab.UPLOAD -> UploadScreen(s) { tab = Tab.REVIEW }
                Tab.REVIEW -> ReviewScreen(s, openReviewId) { openReviewId = null }
                Tab.YOU -> YouScreen(s)
            }
        }
        // Bottom tab bar on white; the active tab gets the mint-soft highlight (MASTER.md "Navigation and layout").
        Row(Modifier.fillMaxWidth().background(Pal.Card).padding(horizontal = 8.dp, vertical = 6.dp)) {
            Tab.entries.forEach { t ->
                val on = t == tab
                Text(t.label, Modifier.weight(1f).heightIn(min = 44.dp).background(if (on) Pal.MintSoft else Color.Transparent, Pal.CtlShape)
                    .clickable { tab = t }.padding(vertical = 12.dp), textAlign = TextAlign.Center,
                    style = Pal.Caption.copy(color = if (on) Pal.MintText else Pal.Muted, fontWeight = FontWeight.Bold))
            }
        }
    }
}

@Composable
private fun YouScreen(s: AppState) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("You", Modifier.padding(top = 16.dp), style = Pal.Title)
        Text("Consent", style = Pal.Caption.copy(fontWeight = FontWeight.Bold))
        ConsentScreen(s)
        Text("Setup", style = Pal.Caption.copy(fontWeight = FontWeight.Bold))
        SetupScreen(s)
        SoftButton("Log out", { s.logout() }, Modifier.fillMaxWidth())
        Text("Logging out discards photos on this phone that were not sent yet.", style = Pal.Caption)
    }
}
