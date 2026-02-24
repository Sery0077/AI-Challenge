package ru.sery0077.aichallenge.util

import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

object MarkdownFormatter {
    fun buildAnnotatedString(text: String): AnnotatedString = buildAnnotatedString {
        val lines = text.split("\n")
        lines.forEachIndexed { index, line ->
            val trimmed = line.trimStart()
            val (style, content) = when {
                trimmed.startsWith("###") -> SpanStyle(
                    fontSize = 18.sp,
                    fontWeight = FontWeight.SemiBold,
                ) to trimmed.removePrefix("###").trimStart()
                trimmed.startsWith("##") -> SpanStyle(
                    fontSize = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                ) to trimmed.removePrefix("##").trimStart()
                trimmed.startsWith("#") -> SpanStyle(
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                ) to trimmed.removePrefix("#").trimStart()
                else -> SpanStyle() to line
            }

            pushStyle(style)
            appendBoldSegments(content)
            pop()

            if (index != lines.lastIndex) {
                append("\n")
            }
        }
    }

    private fun AnnotatedString.Builder.appendBoldSegments(text: String) {
        var index = 0
        while (index < text.length) {
            val nextDoubleAsterisk = text.indexOf("**", index)
            val nextDoubleUnderscore = text.indexOf("__", index)
            val start = when {
                nextDoubleAsterisk == -1 -> nextDoubleUnderscore
                nextDoubleUnderscore == -1 -> nextDoubleAsterisk
                else -> minOf(nextDoubleAsterisk, nextDoubleUnderscore)
            }

            if (start == -1) {
                append(text.substring(index))
                break
            }

            if (start > index) {
                append(text.substring(index, start))
            }

            val delimiter = if (text.startsWith("**", start)) "**" else "__"
            val end = text.indexOf(delimiter, start + 2)
            if (end == -1) {
                append(text.substring(start))
                break
            }

            pushStyle(SpanStyle(fontWeight = FontWeight.Bold))
            append(text.substring(start + 2, end))
            pop()
            index = end + 2
        }
    }
}
