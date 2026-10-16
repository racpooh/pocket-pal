package dev.finassist.android

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/*
 * Design tokens from pocket-pal design-system/pocket-pal/MASTER.md (reference only; no pocket-pal code or demo data).
 * Light mode only. Mint is a fill only (never white text on mint). Red only with words ("Failed", "over").
 * Font: system font for now (Plus Jakarta Sans / Noto Sans Thai are not bundled yet — noted in docs/design/13).
 */
object Pal {
    val Page = Color(0xFFE9EDF0)
    val Bg = Color(0xFFF3F4F6)
    val Card = Color(0xFFFFFFFF)
    val Ink = Color(0xFF111214)
    val Muted = Color(0xFF5B6170)
    val Line = Color(0xFFECEEF1)
    val Mint = Color(0xFF5CC9A0)
    val MintSoft = Color(0xFFE6F7EF)
    val MintText = Color(0xFF0B7A55)
    val Danger = Color(0xFFB91C1C)
    val DangerSoft = Color(0xFFFEF2F2)
    val TestModeBg = Color(0xFFFFE9A8)

    val CardShape = RoundedCornerShape(22.dp)
    val CtlShape = RoundedCornerShape(16.dp)
    val Pill = RoundedCornerShape(50)

    val Title = TextStyle(fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
    val CardTitle = TextStyle(fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.Bold, color = Ink)
    val Body = TextStyle(fontSize = 15.sp, lineHeight = 22.sp, color = Ink)
    val Caption = TextStyle(fontSize = 13.sp, lineHeight = 18.sp, color = Muted)
    val Amount = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
}

@Composable
fun PalTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(primary = Pal.Ink, onPrimary = Color.White, secondary = Pal.Mint, onSecondary = Pal.Ink,
            background = Pal.Bg, surface = Pal.Bg, onSurface = Pal.Ink, error = Pal.Danger),
        content = content,
    )
}

@Composable
fun PalCard(modifier: Modifier = Modifier, flagged: Boolean = false, danger: Boolean = false, onClick: (() -> Unit)? = null,
            content: @Composable ColumnScope.() -> Unit) {
    var m = modifier.fillMaxWidth()
    m = if (danger) m.background(Pal.DangerSoft, Pal.CardShape)
        else if (flagged) m.border(BorderStroke(2.dp, Pal.Ink), Pal.CardShape).background(Pal.Card, Pal.CardShape)
        else m.shadow(4.dp, Pal.CardShape, ambientColor = Color(0x10101828), spotColor = Color(0x10101828)).background(Pal.Card, Pal.CardShape)
    if (onClick != null) m = m.clickable(onClick = onClick)
    Column(m.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content)
}

@Composable
fun HintPill(text: String, modifier: Modifier = Modifier, soft: Color = Pal.MintSoft, fg: Color = Pal.Ink) {
    Text(text, modifier.fillMaxWidth().background(soft, Pal.Pill).padding(horizontal = 12.dp, vertical = 8.dp),
        style = Pal.Caption.copy(color = fg, fontWeight = FontWeight.SemiBold))
}

@Composable
fun Tag(text: String, dark: Boolean = true) {
    Text(text, Modifier.background(if (dark) Pal.Ink else Pal.Bg, Pal.Pill).padding(horizontal = 8.dp, vertical = 2.dp),
        style = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Bold, color = if (dark) Color.White else Pal.Ink))
}

@Composable
fun InkButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, busy: Boolean = false) {
    Button(onClick = onClick, enabled = enabled && !busy, modifier = modifier.fillMaxWidth().heightIn(min = 52.dp), shape = Pal.CtlShape,
        colors = ButtonDefaults.buttonColors(containerColor = Pal.Ink, contentColor = Color.White)) {
        if (busy) CircularProgressIndicator(Modifier.padding(end = 8.dp).size(18.dp), color = Color.White, strokeWidth = 2.dp)
        Text(text, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun MintButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Button(onClick = onClick, enabled = enabled, modifier = modifier.fillMaxWidth().heightIn(min = 52.dp), shape = Pal.CtlShape,
        colors = ButtonDefaults.buttonColors(containerColor = Pal.Mint, contentColor = Pal.Ink)) { Text(text, fontWeight = FontWeight.Bold) }
}

@Composable
fun SoftButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    OutlinedButton(onClick = onClick, enabled = enabled, modifier = modifier.heightIn(min = 44.dp), shape = Pal.CtlShape,
        border = BorderStroke(0.dp, Color.Transparent), contentPadding = PaddingValues(horizontal = 16.dp),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = Pal.Bg, contentColor = Pal.Ink)) { Text(text, fontWeight = FontWeight.SemiBold) }
}

@Composable
fun Chip(text: String, selected: Boolean, onClick: () -> Unit) {
    Text(text, Modifier.background(if (selected) Pal.Ink else Pal.Card, Pal.Pill).clickable(onClick = onClick)
        .heightIn(min = 44.dp).padding(horizontal = 16.dp, vertical = 12.dp),
        style = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = if (selected) Color.White else Pal.Ink))
}

/** Loading / error-with-retry / content, used by every screen that loads from the backend. */
sealed class Load<out T> {
    object Loading : Load<Nothing>()
    data class Failed(val message: String) : Load<Nothing>()
    data class Ready<T>(val value: T) : Load<T>()
}

@Composable
fun <T> LoadBox(state: Load<T>, onRetry: () -> Unit, content: @Composable (T) -> Unit) {
    when (state) {
        is Load.Loading -> Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Pal.Ink) }
        is Load.Failed -> PalCard(Modifier.padding(18.dp), danger = true) {
            Text("Couldn't load", style = Pal.CardTitle.copy(color = Pal.Danger))
            Text(state.message, style = Pal.Body.copy(color = Pal.Danger))
            Row { SoftButton("Retry", onRetry) }
        }
        is Load.Ready -> content(state.value)
    }
}
