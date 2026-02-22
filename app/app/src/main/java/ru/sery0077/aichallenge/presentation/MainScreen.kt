package ru.sery0077.aichallenge.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import org.koin.androidx.compose.koinViewModel
import org.koin.core.context.GlobalContext
import ru.sery0077.aichallenge.domain.model.ChatMessage
import ru.sery0077.aichallenge.domain.model.ChatRole
import ru.sery0077.aichallenge.ui.AppScaffold
import ru.sery0077.aichallenge.ui.theme.AIChallengeTheme
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions

@Composable
fun MainScreen(
    viewModel: MainViewModel = koinViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    val isSheetOpen = remember { mutableStateOf(false) }
    val screenDestination = remember { mutableStateOf(ScreenDestination.Chat) }
    val blocksParser = remember { GlobalContext.get().get<MarkdownBlocksParser>() }

    when (screenDestination.value) {
        ScreenDestination.Chat -> {
            MainScreenContent(
                state = state,
                onPromptChange = viewModel::onPromptChange,
                onSendClick = viewModel::onSendClick,
                onOpenSettings = { isSheetOpen.value = true },
                onCloseSettings = { isSheetOpen.value = false },
                onApplySettings = viewModel::onApplySettings,
                onOpenFormattingPreview = {
                    screenDestination.value = ScreenDestination.FormattingPreview
                },
                isSheetOpen = isSheetOpen.value,
                blocksParser = blocksParser,
            )
        }
        ScreenDestination.FormattingPreview -> {
            FormattingPreviewScreen(
                text = FormattingPreviewText,
                blocksParser = blocksParser,
                onBack = { screenDestination.value = ScreenDestination.Chat },
            )
        }
    }
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
    onOpenFormattingPreview: () -> Unit,
    isSheetOpen: Boolean,
    blocksParser: MarkdownBlocksParser,
) {
    val listState = rememberLazyListState()
    val lastContent = state.messages.lastOrNull()?.content

    LaunchedEffect(state.messages.size, lastContent) {
        if (state.messages.isNotEmpty()) {
            listState.animateScrollToItem(state.messages.lastIndex)
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
                            contentDescription = "Settings",
                        )
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (state.isApiKeyMissing) {
                Text(
                    text = "API key is missing. Set ROUTERAI_API_KEY at build time.",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                )
            }
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                state = listState,
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item {
                    SelectionContainer {
                        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            state.messages.forEachIndexed { index, message ->
                                MessageBubble(
                                    message = message,
                                    isLoading = state.isLoading,
                                    isLast = index == state.messages.lastIndex,
                                    blocksParser = blocksParser,
                                )
                            }
                        }
                    }
                }
            }
            if (state.error != null) {
                Text(
                    text = state.error ?: "",
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                OutlinedTextField(
                    value = state.prompt,
                    onValueChange = onPromptChange,
                    label = { Text("Message") },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    enabled = !state.isLoading,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(
                        onSend = { onSendClick() },
                    ),
                )
                Button(
                    onClick = onSendClick,
                    enabled = !state.isLoading,
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
                ) {
                    Text(if (state.isLoading) "Sending" else "Send")
                }
            }
        }
    }

    SettingsBottomSheet(
        isOpen = isSheetOpen,
        settings = state.settings,
        onDismiss = onCloseSettings,
        onApply = onApplySettings,
        onOpenFormattingPreview = onOpenFormattingPreview,
    )
}

@Composable
private fun MessageBubble(
    message: ChatMessage,
    isLoading: Boolean,
    isLast: Boolean,
    blocksParser: MarkdownBlocksParser,
) {
    val isUser = message.role == ChatRole.User
    val alignment = if (isUser) Arrangement.End else Arrangement.Start
    val bubbleColor = if (isUser) {
        MaterialTheme.colorScheme.primaryContainer
    } else {
        MaterialTheme.colorScheme.surfaceVariant
    }
    val textColor = if (isUser) {
        MaterialTheme.colorScheme.onPrimaryContainer
    } else {
        MaterialTheme.colorScheme.onSurfaceVariant
    }

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = alignment,
    ) {
        val contentText = if (message.content.isBlank() && !isUser && isLoading && isLast) {
            "..."
        } else {
            message.content
        }
        val contentModifier = Modifier
            .widthIn(max = 320.dp)
            .padding(horizontal = 12.dp, vertical = 10.dp)
        if (isUser) {
            Surface(
                color = bubbleColor,
                shape = MaterialTheme.shapes.medium,
                tonalElevation = 1.dp,
            ) {
                Text(text = contentText, color = textColor, modifier = contentModifier)
            }
        } else {
            Surface(
                color = bubbleColor,
                shape = MaterialTheme.shapes.medium,
                tonalElevation = 1.dp,
            ) {
                Column(modifier = contentModifier) {
                    MarkdownMessageRenderer.Render(
                        text = contentText,
                        blocksParser = blocksParser,
                    )
                }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun MainScreenPreview() {
    AIChallengeTheme {
        MainScreenContent(
            state = MainUiState(
                prompt = "Hello!",
                messages = listOf(
                    ChatMessage(ChatRole.User, "Hi there"),
                    ChatMessage(ChatRole.Assistant, "Hello! How can I help you today?"),
                ),
                isLoading = false,
                error = null,
            ),
            onPromptChange = {},
            onSendClick = {},
            onOpenSettings = {},
            onCloseSettings = {},
            onApplySettings = {},
            onOpenFormattingPreview = {},
            isSheetOpen = false,
            blocksParser = MarkdownBlocksParser(),
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun MessageBubblePreview() {
    AIChallengeTheme {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            val blocksParser = MarkdownBlocksParser()
            MessageBubble(
                message = ChatMessage(ChatRole.User, "User message"),
                isLoading = false,
                isLast = false,
                blocksParser = blocksParser,
            )
            MessageBubble(
                message = ChatMessage(ChatRole.Assistant, "Assistant reply with **bold** text"),
                isLoading = false,
                isLast = false,
                blocksParser = blocksParser,
            )
        }
    }
}
