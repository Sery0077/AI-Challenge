package ru.sery0077.aichallenge.feature.chat.domain.usecase

import kotlinx.coroutines.flow.Flow
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatMessage
import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository

class ObserveMessagesUseCase(
    private val repository: ChatHistoryRepository,
) {
    operator fun invoke(sessionId: Long): Flow<List<ChatMessage>> {
        return repository.observeMessages(sessionId)
    }
}
