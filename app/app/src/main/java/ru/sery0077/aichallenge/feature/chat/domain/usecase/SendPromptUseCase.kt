package ru.sery0077.aichallenge.feature.chat.domain.usecase

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatMessage
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatRole
import ru.sery0077.aichallenge.feature.chat.domain.model.RequestSettings
import ru.sery0077.aichallenge.feature.chat.domain.repository.RouterAIRepository

class SendPromptUseCase(
    private val repository: RouterAIRepository,
) {
    operator fun invoke(messages: List<ChatMessage>, settings: RequestSettings): Flow<String> {
        val lastMessage = messages.lastOrNull()
        if (lastMessage == null || lastMessage.role != ChatRole.User || lastMessage.content.isBlank()) {
            return flow { throw IllegalArgumentException("Prompt is blank.") }
        }
        return repository.streamChat(
            messages = messages,
            settings = settings,
        )
    }
}
