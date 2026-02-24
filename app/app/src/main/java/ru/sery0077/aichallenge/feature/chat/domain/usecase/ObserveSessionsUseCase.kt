package ru.sery0077.aichallenge.feature.chat.domain.usecase

import kotlinx.coroutines.flow.Flow
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatSession
import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository

class ObserveSessionsUseCase(
    private val repository: ChatHistoryRepository,
) {
    operator fun invoke(): Flow<List<ChatSession>> = repository.observeSessions()
}
