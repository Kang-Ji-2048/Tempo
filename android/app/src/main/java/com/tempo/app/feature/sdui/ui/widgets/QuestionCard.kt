package com.tempo.app.feature.sdui.ui.widgets

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Send
import androidx.compose.material.icons.rounded.Forum
import androidx.compose.material.icons.rounded.SportsTennis
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.feature.sdui.model.QuestionWidget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.feature.sdui.ui.components.SduiCard
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite

@Composable
fun QuestionCard(
    widget: QuestionWidget,
    onAction: (WidgetAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    var answer by rememberSaveable(widget.key, widget.submittedAnswer) { mutableStateOf(widget.submittedAnswer) }
    var draft by rememberSaveable(widget.key) { mutableStateOf("") }

    val submit: (String) -> Unit = { text ->
        val trimmed = text.trim()
        if (trimmed.isNotEmpty() && answer == null) {
            answer = trimmed
            draft = ""
            onAction(WidgetAction.ChoiceSelected(widgetId = widget.id, freeText = trimmed))
        }
    }

    SduiCard(eyebrow = "Coach asks", icon = Icons.Rounded.Forum, modifier = modifier) {
        Row(verticalAlignment = Alignment.Top) {
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .background(AccentNeonVolt),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Rounded.SportsTennis, null, tint = BackgroundOnyx, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.size(10.dp))
            Text(
                text = widget.prompt,
                color = TextPrimaryWhite,
                fontSize = 16.sp,
                lineHeight = 22.sp,
                modifier = Modifier
                    .clip(RoundedCornerShape(topStart = 4.dp, topEnd = 18.dp, bottomEnd = 18.dp, bottomStart = 18.dp))
                    .background(SurfaceVariantDark)
                    .padding(horizontal = 14.dp, vertical = 12.dp),
            )
        }

        AnimatedVisibility(visible = answer != null, enter = slideInHorizontally { it / 2 } + fadeIn()) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                Text(
                    text = answer.orEmpty(),
                    color = BackgroundOnyx,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 15.sp,
                    modifier = Modifier
                        .widthIn(max = 260.dp)
                        .clip(RoundedCornerShape(topStart = 18.dp, topEnd = 4.dp, bottomEnd = 18.dp, bottomStart = 18.dp))
                        .background(AccentNeonVolt)
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                )
            }
        }

        if (answer == null) {
            if (widget.quickReplies.isNotEmpty()) {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(widget.quickReplies) { reply ->
                        Text(
                            text = reply,
                            color = TextPrimaryWhite,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier
                                .clip(RoundedCornerShape(50))
                                .border(1.dp, AccentNeonVolt.copy(alpha = 0.5f), RoundedCornerShape(50))
                                .clickable { submit(reply) }
                                .padding(horizontal = 14.dp, vertical = 8.dp),
                        )
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    placeholder = { Text(widget.hint, color = TextMuted) },
                    singleLine = true,
                    shape = RoundedCornerShape(16.dp),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = { submit(draft) }),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = AccentNeonVolt,
                        unfocusedBorderColor = CardBorderSubtle,
                        cursorColor = AccentNeonVolt,
                        focusedTextColor = TextPrimaryWhite,
                        unfocusedTextColor = TextPrimaryWhite,
                    ),
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.size(8.dp))
                FilledIconButton(
                    onClick = { submit(draft) },
                    enabled = draft.isNotBlank(),
                    modifier = Modifier.size(52.dp),
                    colors = IconButtonDefaults.filledIconButtonColors(
                        containerColor = AccentNeonVolt,
                        contentColor = BackgroundOnyx,
                        disabledContainerColor = SurfaceVariantDark,
                        disabledContentColor = TextMuted,
                    ),
                ) {
                    Icon(Icons.AutoMirrored.Rounded.Send, contentDescription = "Send answer")
                }
            }
        }
    }
}
