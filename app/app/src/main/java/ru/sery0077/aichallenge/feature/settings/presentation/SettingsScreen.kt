package ru.sery0077.aichallenge.feature.settings.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import ru.sery0077.aichallenge.ui.AppScaffold
import ru.sery0077.aichallenge.ui.theme.AIChallengeTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onOpenFormattingPreview: () -> Unit,
    defaultModel: String,
    sessionModel: String,
    onApplyModels: (String, String) -> Unit,
) {
    val defaultModelState = remember { mutableStateOf(defaultModel) }
    val sessionModelState = remember { mutableStateOf(sessionModel) }

    LaunchedEffect(defaultModel) {
        defaultModelState.value = defaultModel
    }
    LaunchedEffect(sessionModel) {
        sessionModelState.value = sessionModel
    }

    AppScaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                        )
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Models", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(
                value = defaultModelState.value,
                onValueChange = { defaultModelState.value = it },
                label = { Text("Default model") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
            )
            OutlinedTextField(
                value = sessionModelState.value,
                onValueChange = { sessionModelState.value = it },
                label = { Text("Current chat model") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
            )
            Button(
                onClick = { onApplyModels(defaultModelState.value, sessionModelState.value) },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Apply models")
            }
            SettingsRow(
                title = "Formatting preview",
                onClick = onOpenFormattingPreview,
            )
        }
    }
}

@Composable
private fun SettingsRow(
    title: String,
    onClick: () -> Unit,
) {
    Surface(
        shape = MaterialTheme.shapes.medium,
        tonalElevation = 1.dp,
        modifier = Modifier.fillMaxWidth(),
        onClick = onClick,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.weight(1f),
            )
            Icon(
                imageVector = Icons.AutoMirrored.Filled.ArrowForward,
                contentDescription = "Open",
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun SettingsScreenPreview() {
    AIChallengeTheme {
        SettingsScreen(
            onBack = {},
            onOpenFormattingPreview = {},
            defaultModel = "deepseek/deepseek-v3.2",
            sessionModel = "deepseek/deepseek-v3.2",
            onApplyModels = { _, _ -> },
        )
    }
}
