package ru.sery0077.aichallenge.feature.settings.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import ru.sery0077.aichallenge.feature.chat.presentation.MarkdownMessageRenderer
import ru.sery0077.aichallenge.ui.AppScaffold
import ru.sery0077.aichallenge.ui.theme.AIChallengeTheme
import ru.sery0077.aichallenge.util.MarkdownBlocksParser

const val FormattingPreviewText = "Вот решение задачи Roman to Integer на Kotlin:\n\n```kotlin\nclass Solution {\n    fun romanToInt(s: String): Int {\n        val values = mapOf(\n            'I' to 1,\n            'V' to 5,\n            'X' to 10,\n            'L' to 50,\n            'C' to 100,\n            'D' to 500,\n            'M' to 1000\n        )\n        \n        var result = 0\n        var prevValue = 0\n        \n        // Проходим строку справа налево\n        for (i in s.length - 1 downTo 0) {\n            val currentValue = values[s[i]] ?: 0\n            \n            if (currentValue \u003c prevValue) {\n                // Если текущее значение меньше предыдущего, вычитаем его\n                result -= currentValue\n            } else {\n                // Иначе добавляем его\n                result += currentValue\n            }\n            \n            prevValue = currentValue\n        }\n        \n        return result\n    }\n}\n```\n\n**Альтернативное решение с более явной логикой:**\n\n```kotlin\nclass Solution {\n    fun romanToInt(s: String): Int {\n        val map = mapOf(\n            'I' to 1,\n            'V' to 5,\n            'X' to 10,\n            'L' to 50,\n            'C' to 100,\n            'D' to 500,\n            'M' to 1000\n        )\n        \n        var result = 0\n        val n = s.length\n        \n        for (i in 0 until n) {\n            val current = map[s[i]]!!\n            \n            // Проверяем, нужно ли вычитать текущее значение\n            if (i \u003c n - 1 \u0026\u0026 current \u003c map[s[i + 1]]!!) {\n                result -= current\n            } else {\n                result += current\n            }\n        }\n        \n        return result\n    }\n}\n```\n\n**Объяснение алгоритма:**\n\n1. Создаем мапу для соответствия римских цифр их целочисленным значениям\n2. Проходим по строке слева направо\n3. Для каждой цифры проверяем следующую цифру:\n   - Если текущая цифра меньше следующей (например, `IV` или `IX`), то вычитаем ее значение\n   - Иначе добавляем ее значение\n4. Возвращаем итоговую сумму\n\n**Примеры работы:**\n\n- `\"III\"` → 1 + 1 + 1 = 3\n- `\"IV\"` → 5 - 1 = 4\n- `\"IX\"` → 10 - 1 = 9\n- `\"LVIII\"` → 50 + 5 + 1 + 1 + 1 = 58\n- `\"MCMXCIV\"` → 1000 + (1000 - 100) + (100 - 10) + (5 - 1) = 1994\n\n**Сложность:**\n- Время: O(n), где n - длина строки\n- Память: O(1) - используем фиксированный размер мапы"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FormattingPreviewScreen(
    text: String,
    blocksParser: MarkdownBlocksParser,
    onBack: () -> Unit,
) {
    val listState = rememberLazyListState()
    val formatted = remember(text) { text }

    AppScaffold(
        topBar = {
            TopAppBar(
                title = { Text("Formatting Preview") },
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
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            state = listState,
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Column {
                    MarkdownMessageRenderer.Render(
                        text = formatted,
                        blocksParser = blocksParser,
                    )
                }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun FormattingPreviewScreenPreview() {
    AIChallengeTheme {
        FormattingPreviewScreen(
            text = "Text before\n```kotlin\n    class Example\n```\nText after",
            blocksParser = MarkdownBlocksParser(),
            onBack = {},
        )
    }
}
