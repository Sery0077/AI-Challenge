package ru.sery0077.aichallenge.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import org.koin.androidx.compose.koinViewModel
import ru.sery0077.aichallenge.ui.AppScaffold
import ru.sery0077.aichallenge.ui.theme.AIChallengeTheme

@Composable
fun MainScreen(
    viewModel: MainViewModel = koinViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    val isSheetOpen = remember { mutableStateOf(false) }

    MainScreenContent(
        state = state,
        onPromptChange = viewModel::onPromptChange,
        onSendClick = viewModel::onSendClick,
        onOpenSettings = { isSheetOpen.value = true },
        onCloseSettings = { isSheetOpen.value = false },
        onApplySettings = viewModel::onApplySettings,
        isSheetOpen = isSheetOpen.value,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MainScreenContent(
    state: MainUiState,
    onPromptChange: (String) -> Unit,
    onSendClick: () -> Unit,
    onOpenSettings: () -> Unit,
    onCloseSettings: () -> Unit,
    onApplySettings: (MainRequestSettings) -> Unit,
    isSheetOpen: Boolean,
) {
    val scrollState = rememberScrollState()

    val shouldAutoScroll = scrollState.value >= scrollState.maxValue
    LaunchedEffect(state.response, state.error, state.isLoading, shouldAutoScroll) {
        if (shouldAutoScroll) {
            scrollState.animateScrollTo(scrollState.maxValue)
        }
    }

    AppScaffold(
        topBar = {
            TopAppBar(
                title = { Text("AI Challenge") },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(
                            imageVector = Icons.Filled.Settings,
                            contentDescription = "Настройки",
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
                .padding(16.dp)
                .verticalScroll(scrollState),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            OutlinedTextField(
                value = state.prompt,
                onValueChange = onPromptChange,
                label = { Text("Prompt") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3,
                enabled = !state.isLoading,
            )
            if (state.isApiKeyMissing) {
                Text(
                    text = "API key не задан. Установи переменную окружения ROUTERAI_API_KEY при сборке.",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Button(
                onClick = onSendClick,
                enabled = !state.isLoading,
                contentPadding = PaddingValues(vertical = 12.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (state.isLoading) "Отправка..." else "Отправить запрос")
            }
            when {
                state.error != null -> {
                    Text(
                        text = state.error ?: "",
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                state.response.isNotBlank() -> {
                    MarkdownText(text = state.formattedResponse)
                }
            }
        }
    }

    SettingsBottomSheet(
        isOpen = isSheetOpen,
        settings = state.settings,
        onDismiss = onCloseSettings,
        onApply = onApplySettings,
    )
}

@Preview(showBackground = true)
@Composable
private fun MainScreenPreview() {
    AIChallengeTheme {
        MainScreenContent(
            state = MainUiState(
                prompt = "Привет! Это тестовый prompt.",
                response = "Ответ от API появится здесь.",
                isLoading = false,
                error = null,
            ),
            onPromptChange = {},
            onSendClick = {},
            onOpenSettings = {},
            onCloseSettings = {},
            onApplySettings = {},
            isSheetOpen = true,
        )
    }
}
