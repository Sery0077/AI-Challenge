package ru.sery0077.aichallenge.feature.chat.presentation

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.koin.androidx.compose.koinViewModel
import org.koin.core.context.GlobalContext
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatMessage
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatRole
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatSession
import ru.sery0077.aichallenge.feature.settings.presentation.FormattingPreviewScreen
import ru.sery0077.aichallenge.feature.settings.presentation.FormattingPreviewText
import ru.sery0077.aichallenge.feature.settings.presentation.MainRequestSettings
import ru.sery0077.aichallenge.feature.settings.presentation.SettingsBottomSheet
import ru.sery0077.aichallenge.feature.settings.presentation.SettingsScreen
import ru.sery0077.aichallenge.ui.AppScaffold
import ru.sery0077.aichallenge.ui.theme.AIChallengeTheme
import ru.sery0077.aichallenge.util.MarkdownBlocksParser

@Composable
fun MainScreen(
    viewModel: MainViewModel = koinViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    val isSheetOpen = remember { mutableStateOf(false) }
    val screenDestination = remember { mutableStateOf(ScreenDestination.Chat) }
    val blocksParser = remember { GlobalContext.get().get<MarkdownBlocksParser>() }
    val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    when (screenDestination.value) {
        ScreenDestination.Chat -> {
            ModalNavigationDrawer(
                drawerState = drawerState,
                drawerContent = {
                    ModalDrawerSheet {
                        SessionsDrawer(
                            sessions = state.sessions,
                            selectedSessionId = state.selectedSessionId,
                            onNewSession = {
                                viewModel.onNewSessionClick()
                                scope.launch { drawerState.close() }
                            },
                            onSelectSession = { sessionId ->
                                viewModel.onSelectSession(sessionId)
                                scope.launch { drawerState.close() }
                            },
                            onOpenSettings = {
                                screenDestination.value = ScreenDestination.Settings
                                scope.launch { drawerState.close() }
                            },
                        )
                    }
                },
            ) {
                MainScreenContent(
                    state = state,
                    onPromptChange = viewModel::onPromptChange,
                    onSendClick = viewModel::onSendClick,
                    onOpenSettings = { isSheetOpen.value = true },
                    onOpenDrawer = { scope.launch { drawerState.open() } },
                    onCloseSettings = { isSheetOpen.value = false },
                    onApplySettings = viewModel::onApplySettings,
                    isSheetOpen = isSheetOpen.value,
                    blocksParser = blocksParser,
                )
            }
        }
        ScreenDestination.Settings -> {
            SettingsScreen(
                onBack = { screenDestination.value = ScreenDestination.Chat },
                onOpenFormattingPreview = {
                    screenDestination.value = ScreenDestination.FormattingPreview
                },
                defaultModel = state.defaultModel,
                sessionModel = state.sessionModel,
                onApplyModels = viewModel::onApplyModels,
            )
        }
        ScreenDestination.FormattingPreview -> {
            FormattingPreviewScreen(
                text = FormattingPreviewText,
                blocksParser = blocksParser,
                onBack = { screenDestination.value = ScreenDestination.Settings },
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
    onOpenDrawer: () -> Unit,
    onCloseSettings: () -> Unit,
    onApplySettings: (MainRequestSettings) -> Unit,
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
                navigationIcon = {
                    IconButton(onClick = onOpenDrawer) {
                        Icon(
                            imageVector = Icons.Filled.Menu,
                            contentDescription = "Menu",
                        )
                    }
                },
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
        currentModel = state.sessionModel,
        onDismiss = onCloseSettings,
        onApply = onApplySettings,
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
        val showTyping = message.content.isBlank() && !isUser && isLoading && isLast
        val contentModifier = Modifier
            .widthIn(max = 320.dp)
            .padding(horizontal = 12.dp, vertical = 10.dp)
        if (isUser) {
            Surface(
                color = bubbleColor,
                shape = MaterialTheme.shapes.medium,
                tonalElevation = 1.dp,
            ) {
                Text(text = message.content, color = textColor, modifier = contentModifier)
            }
        } else {
            Surface(
                color = bubbleColor,
                shape = MaterialTheme.shapes.medium,
                tonalElevation = 1.dp,
            ) {
                if (showTyping) {
                    TypingDots(
                        modifier = contentModifier,
                        color = textColor,
                    )
                } else {
                    Column(modifier = contentModifier) {
                        MarkdownMessageRenderer.Render(
                            text = message.content,
                            blocksParser = blocksParser,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SessionsDrawer(
    sessions: List<ChatSession>,
    selectedSessionId: Long?,
    onNewSession: () -> Unit,
    onSelectSession: (Long) -> Unit,
    onOpenSettings: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(text = "Sessions", style = MaterialTheme.typography.titleLarge)
        Button(onClick = onNewSession, modifier = Modifier.fillMaxWidth()) {
            Text("New chat")
        }
        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(sessions) { session ->
                val isSelected = session.id == selectedSessionId
                Surface(
                    color = if (isSelected) {
                        MaterialTheme.colorScheme.primaryContainer
                    } else {
                        MaterialTheme.colorScheme.surfaceVariant
                    },
                    shape = MaterialTheme.shapes.medium,
                    tonalElevation = 1.dp,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { onSelectSession(session.id) },
                ) {
                    Text(
                        text = session.title,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                        color = if (isSelected) {
                            MaterialTheme.colorScheme.onPrimaryContainer
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                    )
                }
            }
        }
        SettingsDrawerRow(title = "Settings", onClick = onOpenSettings)
    }
}

@Composable
private fun SettingsDrawerRow(
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

@Composable
private fun TypingDots(
    modifier: Modifier = Modifier,
    color: Color,
) {
    val transition = rememberInfiniteTransition(label = "typing")
    val phase by transition.animateFloat(
        initialValue = 0f,
        targetValue = 3f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 900),
            repeatMode = RepeatMode.Restart,
        ),
        label = "phase",
    )
    val step = phase % 3f
    val alpha1 = if (step >= 0f) 1f else 0.3f
    val alpha2 = if (step >= 1f) 1f else 0.3f
    val alpha3 = if (step >= 2f) 1f else 0.3f
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text = ".", color = color.copy(alpha = alpha1))
        Text(text = ".", color = color.copy(alpha = alpha2))
        Text(text = ".", color = color.copy(alpha = alpha3))
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
                defaultModel = "deepseek/deepseek-v3.2",
                sessionModel = "deepseek/deepseek-v3.2",
                isLoading = false,
                error = null,
            ),
            onPromptChange = {},
            onSendClick = {},
            onOpenSettings = {},
            onOpenDrawer = {},
            onCloseSettings = {},
            onApplySettings = {},
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

@Preview(showBackground = true)
@Composable
private fun SessionsDrawerPreview() {
    AIChallengeTheme {
        SessionsDrawer(
            sessions = listOf(
                ChatSession(1, "New chat", "deepseek/deepseek-v3.2", 0, 0),
                ChatSession(2, "Roman to Integer", "deepseek/deepseek-v3.2", 0, 0),
            ),
            selectedSessionId = 2,
            onNewSession = {},
            onSelectSession = {},
            onOpenSettings = {},
        )
    }
}
