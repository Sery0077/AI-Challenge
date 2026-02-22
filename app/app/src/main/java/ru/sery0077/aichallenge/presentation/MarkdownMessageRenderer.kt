package ru.sery0077.aichallenge.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import ru.sery0077.aichallenge.ui.theme.AIChallengeTheme
import ru.sery0077.aichallenge.ui.theme.CodeBlockBackground
import ru.sery0077.aichallenge.ui.theme.CodeBlockText

object MarkdownMessageRenderer {
    @Composable
    fun Render(
        text: String,
        blocksParser: MarkdownBlocksParser,
        modifier: Modifier = Modifier,
    ) {
        val blocks = remember(text, blocksParser) { blocksParser.parse(text) }
        SelectionContainer {
            Column(
                modifier = modifier,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                blocks.forEach { block ->
                    if (block.isCode) {
                        CodeBlock(text = block.text)
                    } else {
                        val formatted = remember(block.text) {
                            MarkdownFormatter.buildAnnotatedString(block.text)
                        }
                        MarkdownText(text = formatted)
                    }
                }
            }
        }
    }

    @Composable
    private fun CodeBlock(text: String) {
        val scrollState = rememberScrollState()
        Surface(
            color = CodeBlockBackground,
            shape = MaterialTheme.shapes.medium,
            tonalElevation = 1.dp,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = text,
                color = CodeBlockText,
                style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                modifier = Modifier
                    .horizontalScroll(scrollState)
                    .padding(horizontal = 12.dp, vertical = 10.dp),
            )
        }
    }

}

@Preview(showBackground = true)
@Composable
private fun MarkdownMessageRendererPreview() {
    AIChallengeTheme {
        MarkdownMessageRenderer.Render(
            text = "Text before\\n```kotlin\\n    class Example\\n```\\nText after",
            blocksParser = MarkdownBlocksParser(),
            modifier = Modifier.padding(16.dp),
        )
    }
}
