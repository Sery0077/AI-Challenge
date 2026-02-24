package ru.sery0077.aichallenge.di

import androidx.room.Room
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import org.koin.android.ext.koin.androidContext
import org.koin.core.module.dsl.viewModel
import org.koin.dsl.module
import ru.sery0077.aichallenge.feature.chat.data.local.AppDatabase
import ru.sery0077.aichallenge.feature.chat.data.repository.ChatHistoryRepositoryImpl
import ru.sery0077.aichallenge.feature.chat.data.repository.RouterAIConfigRepositoryImpl
import ru.sery0077.aichallenge.feature.chat.data.repository.RouterAIRepositoryImpl
import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository
import ru.sery0077.aichallenge.feature.chat.domain.repository.RouterAIConfigRepository
import ru.sery0077.aichallenge.feature.chat.domain.repository.RouterAIRepository
import ru.sery0077.aichallenge.feature.chat.domain.usecase.CreateSessionUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.GetSessionUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.InsertMessageUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.ObserveMessagesUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.ObserveSessionsUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.SendPromptUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.TouchSessionUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.UpdateSessionModelUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.UpdateSessionTitleUseCase
import ru.sery0077.aichallenge.feature.chat.presentation.MainViewModel
import ru.sery0077.aichallenge.util.CodeIndentNormalizer
import ru.sery0077.aichallenge.util.MarkdownBlocksParser
import ru.sery0077.aichallenge.util.ResponseTextNormalizer
import java.util.concurrent.TimeUnit

val coreModule = module {
    single { provideJson() }
    single { provideOkHttpClient() }
}

val databaseModule = module {
    single {
        Room.databaseBuilder(
            androidContext(),
            AppDatabase::class.java,
            "ai_challenge.db",
        ).build()
    }
    single { get<AppDatabase>().chatSessionDao() }
    single { get<AppDatabase>().chatMessageDao() }
}

val utilModule = module {
    single { CodeIndentNormalizer() }
    single { MarkdownBlocksParser(get()) }
    single { ResponseTextNormalizer() }
}

val chatModule = module {
    single<RouterAIConfigRepository> { RouterAIConfigRepositoryImpl() }
    single<RouterAIRepository> { RouterAIRepositoryImpl(get(), get(), get()) }
    single<ChatHistoryRepository> { ChatHistoryRepositoryImpl(get(), get()) }
    single { SendPromptUseCase(get()) }
    single { ObserveSessionsUseCase(get()) }
    single { ObserveMessagesUseCase(get()) }
    single { CreateSessionUseCase(get()) }
    single { InsertMessageUseCase(get()) }
    single { UpdateSessionTitleUseCase(get()) }
    single { UpdateSessionModelUseCase(get()) }
    single { TouchSessionUseCase(get()) }
    single { GetSessionUseCase(get()) }
    viewModel {
        MainViewModel(
            sendPromptUseCase = get(),
            configRepository = get(),
            responseTextNormalizer = get(),
            observeSessionsUseCase = get(),
            observeMessagesUseCase = get(),
            createSessionUseCase = get(),
            insertMessageUseCase = get(),
            updateSessionTitleUseCase = get(),
            updateSessionModelUseCase = get(),
            touchSessionUseCase = get(),
            getSessionUseCase = get(),
        )
    }
}

val appModules = listOf(
    coreModule,
    databaseModule,
    utilModule,
    chatModule,
)

private fun provideJson(): Json = Json {
    ignoreUnknownKeys = true
    isLenient = true
}

private fun provideOkHttpClient(): OkHttpClient {
    return OkHttpClient.Builder()
        .connectTimeout(180, TimeUnit.SECONDS)
        .readTimeout(180, TimeUnit.SECONDS)
        .writeTimeout(180, TimeUnit.SECONDS)
        .callTimeout(180, TimeUnit.SECONDS)
        .build()
}

// Retrofit setup can be added here later if needed.
