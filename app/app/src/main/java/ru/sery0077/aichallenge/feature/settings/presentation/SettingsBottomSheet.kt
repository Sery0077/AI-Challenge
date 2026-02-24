package ru.sery0077.aichallenge.feature.settings.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import ru.sery0077.aichallenge.ui.theme.AIChallengeTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsBottomSheet(
    isOpen: Boolean,
    settings: MainRequestSettings,
    currentModel: String,
    onDismiss: () -> Unit,
    onApply: (MainRequestSettings) -> Unit,
) {
    if (!isOpen) return

    val maxTokens = remember { mutableStateOf(settings.maxTokens) }
    val temperature = remember { mutableStateOf(settings.temperature) }
    val stop = remember { mutableStateOf(settings.stop) }
    val streamEnabled = remember { mutableStateOf(settings.streamEnabled) }

    LaunchedEffect(settings, isOpen) {
        maxTokens.value = settings.maxTokens
        temperature.value = settings.temperature
        stop.value = settings.stop
        streamEnabled.value = settings.streamEnabled
    }

    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
    )
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Request settings", style = MaterialTheme.typography.titleLarge)

            OutlinedTextField(
                value = maxTokens.value,
                onValueChange = { maxTokens.value = it },
                label = { Text("Max tokens") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                trailingIcon = {
                    InfoIconTooltip(
                        text = "Maximum tokens in the response. Higher values produce longer answers.",
                    )
                },
            )
            OutlinedTextField(
                value = temperature.value,
                onValueChange = { temperature.value = it },
                label = { Text("Temperature") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                trailingIcon = {
                    InfoIconTooltip(
                        text = "Temperature affects creativity. Higher values produce more varied answers.",
                    )
                },
            )
            OutlinedTextField(
                value = stop.value,
                onValueChange = { stop.value = it },
                label = { Text("Stop (comma-separated)") },
                modifier = Modifier.fillMaxWidth(),
                trailingIcon = {
                    InfoIconTooltip(
                        text = "Stop strings halt generation when matched. Example: ###, END",
                    )
                },
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Checkbox(
                    checked = streamEnabled.value,
                    onCheckedChange = { streamEnabled.value = it },
                )
                Text(
                    text = "Stream (partial response)",
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
            Text(
                text = "Current model: $currentModel",
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(
                onClick = {
                    onApply(
                        MainRequestSettings(
                            maxTokens = maxTokens.value,
                            temperature = temperature.value,
                            stop = stop.value,
                            streamEnabled = streamEnabled.value,
                        ),
                    )
                    onDismiss()
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Apply")
            }
        }
    }
}

@Composable
private fun InfoIconTooltip(text: String) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        IconButton(onClick = { expanded = !expanded }) {
            Icon(
                imageVector = Icons.Filled.Info,
                contentDescription = "Hint",
            )
        }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
        ) {
            BubbleTooltip(text = text)
        }
    }
}

@Composable
private fun BubbleTooltip(text: String) {
    Surface(
        tonalElevation = 2.dp,
        shadowElevation = 4.dp,
        modifier = Modifier.width(250.dp),
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier
                .widthIn(min = 100.dp, max = 120.dp)
                .padding(horizontal = 12.dp, vertical = 10.dp),
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun SettingsBottomSheetPreview() {
    AIChallengeTheme {
        SettingsBottomSheet(
            isOpen = true,
            settings = MainRequestSettings(
                maxTokens = "1024",
                temperature = "0.7",
                stop = "###, END",
                streamEnabled = true,
            ),
            currentModel = "deepseek/deepseek-v3.2",
            onDismiss = {},
            onApply = {},
        )
    }
}
